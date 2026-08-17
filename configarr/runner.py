"""Read-only plan runner and the apply path. MUST stay free of generated-client
imports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from configarr.engine import diff, reconcile_renames
from configarr.models import ConfigarrConfig
from configarr.plan import Op, Plan
from configarr.providers.base import ResourceProvider
from configarr.registry import PlannedProvider, providers_for
from configarr.render import ResourceJson, plan_resources_json, render_plan
from configarr.state import State


def _scope(planned: PlannedProvider) -> str:
    return f"{planned.service}/{planned.instance}"


def _managed_keys(state: State | None, planned: PlannedProvider) -> set[Any] | None:
    """Managed-key set for prune scoping, or None to keep legacy delete-any-unmanaged
    behavior. Ownership only matters for prunable providers; others never delete."""
    if state is None or not getattr(planned.provider, "prunable", False):
        return None
    return set(state.managed_keys(_scope(planned), planned.provider.kind))


def _managed_ids(state: State | None, planned: PlannedProvider) -> dict[str, int]:
    """Recorded ``{name: id}`` for a prunable provider, for rename reconciliation."""
    if state is None or not getattr(planned.provider, "prunable", False):
        return {}
    return state.managed_ids(_scope(planned), planned.provider.kind)


def _record_ownership(
    state: State,
    planned: PlannedProvider,
    provider: ResourceProvider,
    desired: list[dict[str, Any]],
    current_by_key: dict[Any, dict[str, Any]],
    applied_ids: dict[Any, int],
    deleted: set[Any],
) -> None:
    """Record the resources a prunable provider manages (everything it declares, minus
    anything just deleted) plus each one's service id, so a later prune is
    ownership-scoped and rename-tolerant. Called for every provider that runs —
    including one that failed mid-apply — so on-disk state never lags what was already
    written to the server."""
    scope, kind = _scope(planned), provider.kind
    prior = state.managed_keys(scope, kind)
    desired_keys = {provider.match_key(d) for d in desired}
    state.set_managed(scope, kind, (prior | desired_keys) - deleted)
    # Record each managed resource's service id (from the write, or from the matched
    # current) so a later run can recognize it after a server rename.
    for d in desired:
        key = provider.match_key(d)
        sid = applied_ids.get(key)
        if sid is None:
            cur = current_by_key.get(key)
            if isinstance(cur, dict) and isinstance(cur.get("id"), int):
                sid = cur["id"]
        if sid is not None:
            state.set_id(scope, kind, str(key), sid)


class ProviderJson(TypedDict):
    service: str
    instance: str
    kind: str
    label: str
    resources: list[ResourceJson]


class PlanDocument(TypedDict):
    has_changes: bool
    providers: list[ProviderJson]


def _diff_provider(
    provider: ResourceProvider,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    prune: bool = False,
    managed_keys: set[Any] | None = None,
    force_update: set[Any] | None = None,
) -> Plan:
    """Diff a provider's already-fetched current/desired exactly as the runner does,
    honoring the opt-in full_replace flag so plan and apply never diverge on diff
    semantics. ``prune`` enables opt-in deletion; ``managed_keys`` scopes that
    deletion to resources configarr owns; ``force_update`` marks reconciled renames
    that must be written even without a field diff (see ``configarr.state``)."""
    return diff(
        provider.kind,
        current,
        desired,
        match_key=provider.match_key,
        normalize=provider.normalize,
        # Full-replace providers opt in so the engine surfaces current-only keys;
        # the schema-overlay CF pilot leaves it unset (additive default).
        full_replace=getattr(provider, "full_replace", False),
        # Only providers that expose deletion participate in --prune; singletons
        # and set-only/config providers stay additive even when prune is asked for.
        prune=prune and getattr(provider, "prunable", False),
        managed_keys=managed_keys,
        force_update=force_update,
    )


def _plan_provider(
    provider: ResourceProvider,
    prune: bool = False,
    managed_keys: set[Any] | None = None,
    managed_ids: dict[str, int] | None = None,
) -> Plan:
    """Diff a single provider exactly as the runner does (read-only plan path)."""
    current = provider.fetch_current()
    desired = provider.build_desired()
    # Relabel any server-renamed managed resource so the plan shows it as an UPDATE
    # (rename) rather than a create-plus-orphan.
    current, renamed = reconcile_renames(
        current, desired, managed_ids or {}, key=provider.match_key
    )
    return _diff_provider(
        provider,
        current,
        desired,
        prune=prune,
        managed_keys=managed_keys,
        force_update=renamed,
    )


def run_plan(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
    prune: bool = False,
    output: str = "text",
    state_path: Path | None = None,
) -> str:
    """Render a read-only plan. ``output`` is "text" (human) or "json" (a stable,
    machine-readable document for CI/automation drift gating). ``state_path`` scopes
    prune deletions to configarr-owned resources; the plan never writes state."""
    state = State.load(state_path) if state_path else None
    planned_plans: list[tuple[PlannedProvider, Plan]] = [
        (
            planned,
            _plan_provider(
                planned.provider,
                prune=prune,
                managed_keys=_managed_keys(state, planned),
                managed_ids=_managed_ids(state, planned),
            ),
        )
        for planned in providers_for(config, service, instance)
    ]
    if output == "json":
        return _plan_json(planned_plans)

    sections: list[str] = []
    for planned, plan in planned_plans:
        sections.append(f"{planned.service}/{planned.instance} — {planned.label}")
        sections.append(render_plan(plan))
    if not sections:
        return "No supported resources configured for --plan."
    return "\n".join(sections)


def _plan_json(planned_plans: list[tuple[PlannedProvider, Plan]]) -> str:
    providers: list[ProviderJson] = [
        ProviderJson(
            service=planned.service,
            instance=planned.instance,
            kind=planned.provider.kind,
            label=planned.label,
            resources=plan_resources_json(plan),
        )
        for planned, plan in planned_plans
    ]
    document: PlanDocument = {
        "has_changes": any(p["resources"] for p in providers),
        "providers": providers,
    }
    # default=str keeps non-JSON-native diff values (e.g. a tuple match key)
    # serializable rather than raising.
    return json.dumps(document, indent=2, default=str)


def run_apply(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
    prune: bool = False,
    state_path: Path | None = None,
) -> str:
    """Execute each provider's plan provider-by-provider in registry order, which
    orders custom formats before quality profiles so ``custom_format_scores`` resolve.
    Each changed resource is turned into an Action and written via the provider's
    apply(). With ``prune`` set, the plan also emits DELETE for unmanaged resources;
    default stays additive.

    ``state_path`` enables ownership tracking: prune only deletes resources configarr
    previously created (recorded in the state file), and after a successful run the
    state is rewritten with the resources configarr now manages.

    Apply is **not atomic**: providers write in sequence with no rollback. If a write
    fails mid-run, the changes already made are surfaced in the raised error so the
    operator knows the partial state, then the error propagates (exit 1). State is
    saved even on a mid-run failure (in a ``finally``), so the ownership of resources
    already written — by completed providers and by the failing one before it aborted
    — is never lost."""
    state = State.load(state_path) if state_path else None
    sections: list[str] = []
    try:
        for planned in providers_for(config, service, instance):
            provider = planned.provider
            label = f"{planned.service}/{planned.instance} — {planned.label}"
            prunable = getattr(provider, "prunable", False)
            # This is the write path, so let tag resolution create missing tags
            # rather than only warn (plan leaves the flag False). Harmless on
            # providers without tags. setattr (not a plain assignment) because the
            # flag is an HttpProvider detail, not on the ResourceProvider protocol.
            setattr(provider, "_create_missing_tags", True)  # noqa: B010
            # Build current and desired exactly once, then diff and derive the apply
            # payloads from the SAME objects. This closes a TOCTOU gap: re-calling
            # build_desired() for the action payloads could observe state that diverged
            # from what the plan was computed against. fetch_current() is memoized, so
            # threading these issues no extra GETs either.
            current = provider.fetch_current()
            desired = provider.build_desired()
            # Relabel a server-renamed managed resource to its desired name so it is
            # updated in place (rename) rather than duplicated. No-op when there's no
            # state or the provider isn't prunable.
            current, renamed = reconcile_renames(
                current, desired, _managed_ids(state, planned), key=provider.match_key
            )
            plan = _diff_provider(
                provider,
                current,
                desired,
                prune=prune,
                managed_keys=_managed_keys(state, planned),
                force_update=renamed,
            )
            current_by_key = {provider.match_key(c): c for c in current}
            desired_by_key = {provider.match_key(d): d for d in desired}
            applied = 0
            deleted: set[Any] = set()
            applied_ids: dict[Any, int] = {}
            try:
                for resource in plan.resources:
                    if not resource.changed:
                        continue
                    action = provider.to_action(
                        resource,
                        current_by_key.get(resource.key),
                        desired_by_key.get(resource.key),
                    )
                    service_id = provider.apply(action)
                    if resource.op is Op.DELETE:
                        deleted.add(resource.key)
                    elif service_id is not None:
                        applied_ids[resource.key] = service_id
                    applied += 1
            except Exception as exc:
                # Surface everything already written (completed providers + this one's
                # partial count) so a mid-run failure isn't silent about the state left.
                partial = f"{label}: applied {applied} change(s), then FAILED"
                already = "\n".join([*sections, partial]) or "(nothing)"
                raise RuntimeError(
                    f"apply aborted at {label}: {exc}\n"
                    f"Applied before the failure:\n{already}"
                ) from exc
            finally:
                # Record ownership of everything this prunable provider declares (even
                # when nothing changed), minus anything just deleted, so a later prune
                # can remove a resource this config drops — and only such resources.
                # In a ``finally`` so a provider that aborts mid-apply still records the
                # ids it wrote before failing.
                if state is not None and prunable:
                    _record_ownership(
                        state,
                        planned,
                        provider,
                        desired,
                        current_by_key,
                        applied_ids,
                        deleted,
                    )
            if applied:
                sections.append(f"{label}: applied {applied} change(s)")
    finally:
        # Persist whatever ownership was recorded, on success or a mid-run abort.
        if state is not None:
            state.save()
    if not sections:
        return "No changes to apply."
    return "\n".join(sections)
