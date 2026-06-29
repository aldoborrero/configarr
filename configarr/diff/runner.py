"""Read-only plan runner. MUST stay free of generated-client imports."""

from __future__ import annotations

from configarr.diff.engine import diff
from configarr.diff.providers.radarr_custom_formats import RadarrCustomFormatProvider
from configarr.diff.render import render_plan
from configarr.models import ConfigarrConfig


def run_plan(config: ConfigarrConfig) -> str:
    if not config.radarr:
        return "No supported resources configured for --plan."
    sections: list[str] = []
    for inst in config.radarr:
        provider = RadarrCustomFormatProvider(
            inst.base_url, inst.api_key, inst.custom_formats
        )
        plan = diff(
            provider.kind,
            provider.fetch_current(),
            provider.build_desired(),
            match_key=provider.match_key,
            normalize=provider.normalize,
        )
        sections.append(f"radarr/{inst.name} — custom formats")
        sections.append(render_plan(plan))
    return "\n".join(sections)
