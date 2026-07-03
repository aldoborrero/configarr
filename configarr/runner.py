"""Read-only plan runner and the apply path. MUST stay free of generated-client
imports."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from configarr.engine import diff
from configarr.model import Plan
from configarr.models import ConfigarrConfig
from configarr.providers.base import ResourceProvider
from configarr.registry import PlannedProvider, providers_for
from configarr.render import ResourceJson, plan_resources_json, render_plan


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
) -> Plan:
    """Diff a provider's already-fetched current/desired exactly as the runner does,
    honoring the opt-in full_replace flag so plan and apply never diverge on diff
    semantics. ``prune`` enables opt-in deletion of unmanaged resources (default
    additive)."""
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
    )


def _plan_provider(provider: ResourceProvider, prune: bool = False) -> Plan:
    """Diff a single provider exactly as the runner does (read-only plan path)."""
    return _diff_provider(
        provider, provider.fetch_current(), provider.build_desired(), prune=prune
    )


def run_plan(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
    prune: bool = False,
    output: str = "text",
) -> str:
    """Render a read-only plan. ``output`` is "text" (human) or "json" (a stable,
    machine-readable document for CI/automation drift gating)."""
    planned_plans: list[tuple[PlannedProvider, Plan]] = [
        (planned, _plan_provider(planned.provider, prune=prune))
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
) -> str:
    """Execute each provider's plan provider-by-provider in registry order, which
    orders custom formats before quality profiles so ``custom_format_scores`` resolve.
    Each changed resource is turned into an Action and written via the provider's
    apply(). With ``prune`` set, the plan also emits DELETE for unmanaged resources;
    default stays additive.

    Apply is **not atomic**: providers write in sequence with no rollback. If a write
    fails mid-run, the changes already made are surfaced in the raised error so the
    operator knows the partial state, then the error propagates (exit 1)."""
    sections: list[str] = []
    for planned in providers_for(config, service, instance):
        provider = planned.provider
        label = f"{planned.service}/{planned.instance} — {planned.label}"
        # Build current and desired exactly once, then diff and derive the apply
        # payloads from the SAME objects. This closes a TOCTOU gap: re-calling
        # build_desired() for the action payloads could observe state that diverged
        # from what the plan was computed against. fetch_current() is memoized, so
        # threading these issues no extra GETs either.
        current = provider.fetch_current()
        desired = provider.build_desired()
        plan = _diff_provider(provider, current, desired, prune=prune)
        current_by_key = {provider.match_key(c): c for c in current}
        desired_by_key = {provider.match_key(d): d for d in desired}
        applied = 0
        try:
            for resource in plan.resources:
                if not resource.changed:
                    continue
                action = provider.to_action(
                    resource,
                    current_by_key.get(resource.key),
                    desired_by_key.get(resource.key),
                )
                provider.apply(action)
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
        if applied:
            sections.append(f"{label}: applied {applied} change(s)")
    if not sections:
        return "No changes to apply."
    return "\n".join(sections)
