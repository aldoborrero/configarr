"""Provider registry: maps resource kinds to provider factories and yields the
provider instances to plan for a config, honoring optional service/instance
filters. Stays client-free (no generated-client imports)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from configarr.models import ConfigarrConfig
from configarr.providers.applications import ApplicationProvider
from configarr.providers.base import ResourceProvider
from configarr.providers.bazarr_language_profiles import (
    BazarrLanguageProfileProvider,
)
from configarr.providers.bazarr_providers import BazarrProviderProvider
from configarr.providers.bazarr_settings import BazarrSettingsProvider
from configarr.providers.delay_profiles import DelayProfileProvider
from configarr.providers.download_clients import DownloadClientProvider
from configarr.providers.indexers import IndexerProvider
from configarr.providers.naming import NamingProvider
from configarr.providers.notifications import NotificationProvider
from configarr.providers.prowlarr_download_clients import (
    ProwlarrDownloadClientProvider,
)
from configarr.providers.quality_definitions import QualityDefinitionProvider
from configarr.providers.quality_profiles import QualityProfileProvider
from configarr.providers.radarr_custom_formats import RadarrCustomFormatProvider
from configarr.providers.release_profiles import ReleaseProfileProvider
from configarr.providers.root_folders import RootFolderProvider
from configarr.providers.sabnzbd_categories import SabnzbdCategoryProvider
from configarr.providers.sabnzbd_misc import SabnzbdMiscProvider
from configarr.providers.sabnzbd_servers import SabnzbdServerProvider


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
    Registration(
        kind="radarr.quality_definition",
        service="radarr",
        label="quality definitions",
        factory=lambda inst: QualityDefinitionProvider(
            inst.base_url,
            inst.api_key,
            inst.quality_definitions,
            "radarr.quality_definition",
        ),
    ),
    Registration(
        kind="sonarr.quality_definition",
        service="sonarr",
        label="quality definitions",
        factory=lambda inst: QualityDefinitionProvider(
            inst.base_url,
            inst.api_key,
            inst.quality_definitions,
            "sonarr.quality_definition",
        ),
    ),
    Registration(
        kind="radarr.naming",
        service="radarr",
        label="naming",
        factory=lambda inst: NamingProvider(
            inst.base_url, inst.api_key, inst.naming_config, "radarr.naming"
        ),
    ),
    Registration(
        kind="sonarr.naming",
        service="sonarr",
        label="naming",
        factory=lambda inst: NamingProvider(
            inst.base_url, inst.api_key, inst.naming_config, "sonarr.naming"
        ),
    ),
    Registration(
        kind="radarr.root_folder",
        service="radarr",
        label="root folders",
        factory=lambda inst: RootFolderProvider(
            inst.base_url, inst.api_key, inst.root_folders, "radarr.root_folder"
        ),
    ),
    Registration(
        kind="sonarr.root_folder",
        service="sonarr",
        label="root folders",
        factory=lambda inst: RootFolderProvider(
            inst.base_url, inst.api_key, inst.root_folders, "sonarr.root_folder"
        ),
    ),
    Registration(
        kind="radarr.delay_profile",
        service="radarr",
        label="delay profiles",
        factory=lambda inst: DelayProfileProvider(
            inst.base_url, inst.api_key, inst.delay_profiles, "radarr.delay_profile"
        ),
    ),
    Registration(
        kind="sonarr.delay_profile",
        service="sonarr",
        label="delay profiles",
        factory=lambda inst: DelayProfileProvider(
            inst.base_url, inst.api_key, inst.delay_profiles, "sonarr.delay_profile"
        ),
    ),
    # Sonarr-only: Radarr ignores release_profiles entirely.
    Registration(
        kind="sonarr.release_profile",
        service="sonarr",
        label="release profiles",
        factory=lambda inst: ReleaseProfileProvider(
            inst.base_url, inst.api_key, inst.release_profiles, "sonarr.release_profile"
        ),
    ),
    Registration(
        kind="radarr.download_client",
        service="radarr",
        label="download clients",
        factory=lambda inst: DownloadClientProvider(
            inst.base_url, inst.api_key, inst.download_clients, "radarr.download_client"
        ),
    ),
    Registration(
        kind="sonarr.download_client",
        service="sonarr",
        label="download clients",
        factory=lambda inst: DownloadClientProvider(
            inst.base_url, inst.api_key, inst.download_clients, "sonarr.download_client"
        ),
    ),
    Registration(
        kind="radarr.notification",
        service="radarr",
        label="notifications",
        factory=lambda inst: NotificationProvider(
            inst.base_url, inst.api_key, inst.notifications, "radarr.notification"
        ),
    ),
    Registration(
        kind="sonarr.notification",
        service="sonarr",
        label="notifications",
        factory=lambda inst: NotificationProvider(
            inst.base_url, inst.api_key, inst.notifications, "sonarr.notification"
        ),
    ),
    # Prowlarr-only: indexers are the first Prowlarr resource in the rollout.
    Registration(
        kind="prowlarr.indexer",
        service="prowlarr",
        label="indexers",
        factory=lambda inst: IndexerProvider(
            inst.base_url, inst.api_key, inst.indexers, "prowlarr.indexer"
        ),
    ),
    # Prowlarr applications: after indexers, both Prowlarr-only.
    Registration(
        kind="prowlarr.application",
        service="prowlarr",
        label="applications",
        factory=lambda inst: ApplicationProvider(
            inst.base_url, inst.api_key, inst.applications, "prowlarr.application"
        ),
    ),
    # Prowlarr download clients: after applications, Prowlarr-only. Uses the
    # generic /api/v1 download-client resource with case-insensitive matching.
    Registration(
        kind="prowlarr.download_client",
        service="prowlarr",
        label="download clients",
        factory=lambda inst: ProwlarrDownloadClientProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "prowlarr.download_client",
        ),
    ),
    # SABnzbd news servers: the first SABnzbd resource. Set-only config API, so
    # the engine GETs the full config and diffs client-side (work-list #12).
    Registration(
        kind="sabnzbd.server",
        service="sabnzbd",
        label="servers",
        factory=lambda inst: SabnzbdServerProvider(
            inst.base_url, inst.api_key, inst.servers, "sabnzbd.server"
        ),
    ),
    # SABnzbd categories: after servers, same set-only config API (work-list #13).
    Registration(
        kind="sabnzbd.category",
        service="sabnzbd",
        label="categories",
        factory=lambda inst: SabnzbdCategoryProvider(
            inst.base_url, inst.api_key, inst.categories, "sabnzbd.category"
        ),
    ),
    # SABnzbd misc settings: the global-settings singleton, same set-only config
    # API written per keyword/value (work-list #14).
    Registration(
        kind="sabnzbd.misc",
        service="sabnzbd",
        label="misc settings",
        factory=lambda inst: SabnzbdMiscProvider(
            inst.base_url, inst.api_key, inst.misc, "sabnzbd.misc"
        ),
    ),
    # Bazarr settings sections: general/sonarr/radarr each own one section of the
    # /system/settings document, written via a partial form-POST (work-list #15).
    Registration(
        kind="bazarr.general",
        service="bazarr",
        label="general settings",
        factory=lambda inst: BazarrSettingsProvider(
            inst.base_url, inst.api_key, inst.general, "bazarr.general"
        ),
    ),
    Registration(
        kind="bazarr.sonarr",
        service="bazarr",
        label="sonarr settings",
        factory=lambda inst: BazarrSettingsProvider(
            inst.base_url, inst.api_key, inst.sonarr, "bazarr.sonarr"
        ),
    ),
    Registration(
        kind="bazarr.radarr",
        service="bazarr",
        label="radarr settings",
        factory=lambda inst: BazarrSettingsProvider(
            inst.base_url, inst.api_key, inst.radarr, "bazarr.radarr"
        ),
    ),
    # Bazarr subtitle providers: each configured provider owns one section of the
    # same /system/settings document, with enabled_providers force-managed
    # additively (work-list #16).
    Registration(
        kind="bazarr.provider",
        service="bazarr",
        label="subtitle providers",
        factory=lambda inst: BazarrProviderProvider(
            inst.base_url, inst.api_key, inst.providers, "bazarr.provider"
        ),
    ),
    # Bazarr language profiles: rebuilt from config and written via the batch
    # languages-profiles form-POST; server-only profiles are preserved (work-list
    # #17).
    Registration(
        kind="bazarr.language_profile",
        service="bazarr",
        label="language profiles",
        factory=lambda inst: BazarrLanguageProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.language_profiles,
            "bazarr.language_profile",
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
