"""Read-only plan runner and the apply path. MUST stay free of generated-client
imports."""

from __future__ import annotations

from configarr.diff.engine import diff
from configarr.diff.model import Plan
from configarr.diff.registry import providers_for
from configarr.diff.render import render_plan
from configarr.models import ConfigarrConfig


def _plan_provider(provider) -> Plan:
    """Diff a single provider exactly as the runner does, honoring the opt-in
    full_replace flag so plan and apply never diverge on diff semantics."""
    return diff(
        provider.kind,
        provider.fetch_current(),
        provider.build_desired(),
        match_key=provider.match_key,
        normalize=provider.normalize,
        # Full-replace providers opt in so the engine surfaces current-only keys;
        # the schema-overlay CF pilot leaves it unset (additive default).
        full_replace=getattr(provider, "full_replace", False),
    )


def run_plan(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
) -> str:
    sections: list[str] = []
    for planned in providers_for(config, service, instance):
        plan = _plan_provider(planned.provider)
        sections.append(f"{planned.service}/{planned.instance} — {planned.label}")
        sections.append(render_plan(plan))
    if not sections:
        return "No supported resources configured for --plan."
    return "\n".join(sections)


def run_apply(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
) -> str:
    """Execute each provider's plan provider-by-provider in registry order, which
    encodes the safe dependency order (custom formats before quality profiles,
    SABnzbd categories before *arr apps, etc.). Each changed resource is turned
    into an Action and written via the provider's apply()."""
    sections: list[str] = []
    for planned in providers_for(config, service, instance):
        provider = planned.provider
        plan = _plan_provider(provider)
        # fetch_current() is memoized, so threading the matched current/desired
        # objects for to_action issues no extra GETs.
        current_by_key = {provider.match_key(c): c for c in provider.fetch_current()}
        desired_by_key = {provider.match_key(d): d for d in provider.build_desired()}
        applied = 0
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
        if applied:
            sections.append(
                f"{planned.service}/{planned.instance} — {planned.label}: "
                f"applied {applied} change(s)"
            )
    if not sections:
        return "No changes to apply."
    return "\n".join(sections)
