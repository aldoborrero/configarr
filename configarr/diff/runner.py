"""Read-only plan runner. MUST stay free of generated-client imports."""

from __future__ import annotations

from configarr.diff.engine import diff
from configarr.diff.registry import providers_for
from configarr.diff.render import render_plan
from configarr.models import ConfigarrConfig


def run_plan(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
) -> str:
    sections: list[str] = []
    for planned in providers_for(config, service, instance):
        provider = planned.provider
        plan = diff(
            provider.kind,
            provider.fetch_current(),
            provider.build_desired(),
            match_key=provider.match_key,
            normalize=provider.normalize,
            # Full-replace providers opt in so the engine surfaces current-only keys;
            # the schema-overlay CF pilot leaves it unset (additive default).
            full_replace=getattr(provider, "full_replace", False),
        )
        sections.append(f"{planned.service}/{planned.instance} — {planned.label}")
        sections.append(render_plan(plan))
    if not sections:
        return "No supported resources configured for --plan."
    return "\n".join(sections)
