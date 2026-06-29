"""Provider registry: maps resource kinds to provider factories and yields the
provider instances to plan for a config, honoring optional service/instance
filters. Stays client-free (no generated-client imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

from configarr.diff.providers.base import ResourceProvider
from configarr.diff.providers.quality_profiles import QualityProfileProvider
from configarr.diff.providers.radarr_custom_formats import RadarrCustomFormatProvider
from configarr.models import ConfigarrConfig


@dataclass(frozen=True)
class Registration:
    """One registered provider: which service/kind it serves and how to build it
    from a single instance config."""

    kind: str
    service: str
    label: str
    factory: Callable[[Any], ResourceProvider]


@dataclass(frozen=True)
class PlannedProvider:
    """A provider bound to a concrete instance, ready to plan."""

    service: str
    instance: str
    label: str
    provider: ResourceProvider


REGISTRY: list[Registration] = [
    Registration(
        kind="radarr.custom_format",
        service="radarr",
        label="custom formats",
        factory=lambda inst: RadarrCustomFormatProvider(
            inst.base_url, inst.api_key, inst.custom_formats
        ),
    ),
    # Quality profiles after custom formats: FormatItems must reference every CF
    # on the instance, so the CFs must exist first.
    Registration(
        kind="radarr.quality_profile",
        service="radarr",
        label="quality profiles",
        factory=lambda inst: QualityProfileProvider(
            inst.base_url, inst.api_key, inst.quality_profiles, "radarr.quality_profile"
        ),
    ),
    Registration(
        kind="sonarr.quality_profile",
        service="sonarr",
        label="quality profiles",
        factory=lambda inst: QualityProfileProvider(
            inst.base_url, inst.api_key, inst.quality_profiles, "sonarr.quality_profile"
        ),
    ),
]


def providers_for(
    config: ConfigarrConfig,
    service: str | None = None,
    instance: str | None = None,
) -> Iterator[PlannedProvider]:
    """Yield a PlannedProvider for every registered provider that matches the
    optional service/instance filters, in registry then instance order."""
    svc_filter = service.lower() if service else None
    for reg in REGISTRY:
        if svc_filter and reg.service != svc_filter:
            continue
        for inst in getattr(config, reg.service):
            if instance and inst.name != instance:
                continue
            yield PlannedProvider(
                service=reg.service,
                instance=inst.name,
                label=reg.label,
                provider=reg.factory(inst),
            )
