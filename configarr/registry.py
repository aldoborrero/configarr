"""Provider registry: maps resource kinds to provider factories and yields the
provider instances to plan for a config, honoring optional service/instance
filters. Stays client-free (no generated-client imports)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from configarr.models import ConfigarrConfig
from configarr.providers.arr.custom_formats import CustomFormatProvider
from configarr.providers.arr.delay_profiles import DelayProfileProvider
from configarr.providers.arr.download_clients import DownloadClientProvider
from configarr.providers.arr.import_lists import ImportListProvider
from configarr.providers.arr.naming import NamingProvider
from configarr.providers.arr.notifications import NotificationProvider
from configarr.providers.arr.quality_definitions import QualityDefinitionProvider
from configarr.providers.arr.quality_profiles import QualityProfileProvider
from configarr.providers.arr.release_profiles import ReleaseProfileProvider
from configarr.providers.arr.root_folders import RootFolderProvider
from configarr.providers.base import ResourceProvider
from configarr.providers.bazarr.language_profiles import (
    BazarrLanguageProfileProvider,
)
from configarr.providers.bazarr.providers import BazarrProviderProvider
from configarr.providers.bazarr.settings import BazarrSettingsProvider
from configarr.providers.bookshelf.metadata_profiles import MetadataProfileProvider
from configarr.providers.bookshelf.root_folders import BookshelfRootFolderProvider
from configarr.providers.cleanuparr.cleaner import (
    CleanuparrClientSettingsProvider,
    CleanuparrSeedingRuleProvider,
)
from configarr.providers.cleanuparr.collections import (
    CleanuparrArrInstanceProvider,
    CleanuparrDownloadClientProvider,
)
from configarr.providers.cleanuparr.sections import (
    CleanuparrArrSettingsProvider,
    CleanuparrSectionProvider,
)
from configarr.providers.kapowarr.collections import (
    KapowarrCredentialProvider,
    KapowarrDownloadClientProvider,
    KapowarrRootFolderProvider,
)
from configarr.providers.kapowarr.settings import KapowarrSettingsProvider
from configarr.providers.kavita.libraries import KavitaLibraryProvider
from configarr.providers.kavita.settings import KavitaSettingsProvider
from configarr.providers.lingarr.onboarding import LingarrOnboardingProvider
from configarr.providers.lingarr.settings import LingarrSettingsProvider
from configarr.providers.prowlarr.applications import ApplicationProvider
from configarr.providers.prowlarr.download_clients import (
    ProwlarrDownloadClientProvider,
)
from configarr.providers.prowlarr.indexers import IndexerProvider
from configarr.providers.sabnzbd.categories import SabnzbdCategoryProvider
from configarr.providers.sabnzbd.misc import SabnzbdMiscProvider
from configarr.providers.sabnzbd.servers import SabnzbdServerProvider
from configarr.providers.tranga.collections import (
    TrangaFileLibraryProvider,
    TrangaLibraryConnectorProvider,
    TrangaNotificationConnectorProvider,
)
from configarr.providers.tranga.settings import TrangaSettingsProvider
from configarr.scope import in_scope


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


# Bookshelf serves the Readarr API, one version below Radarr/Sonarr's /api/v3.
BOOKSHELF_API = "/api/v1"

REGISTRY: list[Registration] = [
    Registration(
        kind="radarr.custom_format",
        service="radarr",
        label="custom formats",
        factory=lambda inst: CustomFormatProvider(
            inst.base_url, inst.api_key, inst.custom_formats, "radarr.custom_format"
        ),
    ),
    # Quality profiles after custom formats: FormatItems must reference every CF
    # on the instance, so the CFs must exist first.
    Registration(
        kind="radarr.quality_profile",
        service="radarr",
        label="quality profiles",
        factory=lambda inst: QualityProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.quality_profiles,
            "radarr.quality_profile",
            pending_formats=inst.custom_formats or {},
        ),
    ),
    Registration(
        kind="sonarr.custom_format",
        service="sonarr",
        label="custom formats",
        factory=lambda inst: CustomFormatProvider(
            inst.base_url, inst.api_key, inst.custom_formats, "sonarr.custom_format"
        ),
    ),
    # Quality profiles after custom formats (see the radarr note above).
    Registration(
        kind="sonarr.quality_profile",
        service="sonarr",
        label="quality profiles",
        factory=lambda inst: QualityProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.quality_profiles,
            "sonarr.quality_profile",
            pending_formats=inst.custom_formats or {},
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
    Registration(
        kind="radarr.import_list",
        service="radarr",
        label="import lists",
        factory=lambda inst: ImportListProvider(
            inst.base_url, inst.api_key, inst.import_lists, "radarr.import_list"
        ),
    ),
    Registration(
        kind="sonarr.import_list",
        service="sonarr",
        label="import lists",
        factory=lambda inst: ImportListProvider(
            inst.base_url, inst.api_key, inst.import_lists, "sonarr.import_list"
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
    Registration(
        kind="bazarr.subsync",
        service="bazarr",
        label="subsync settings",
        factory=lambda inst: BazarrSettingsProvider(
            inst.base_url, inst.api_key, inst.subsync, "bazarr.subsync"
        ),
    ),
    Registration(
        kind="bazarr.translator",
        service="bazarr",
        label="translator settings",
        factory=lambda inst: BazarrSettingsProvider(
            inst.base_url, inst.api_key, inst.translator, "bazarr.translator"
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
    # Lingarr's flat settings store, split into two logical groups. Both hit the same
    # /api/setting endpoints; each owns its own known-key set (translation before
    # integration is cosmetic — they're independent singletons).
    # Onboarding first: a fresh Lingarr 403s every settings call until it has run.
    Registration(
        kind="lingarr.onboarding",
        service="lingarr",
        label="onboarding",
        factory=lambda inst: LingarrOnboardingProvider(
            inst.base_url, inst.api_key, inst.onboarding, "lingarr.onboarding"
        ),
    ),
    Registration(
        kind="lingarr.translation",
        service="lingarr",
        label="translation settings",
        factory=lambda inst: LingarrSettingsProvider(
            inst.base_url,
            inst.api_key,
            inst.translation,
            "lingarr.translation",
            onboarding_managed=inst.onboarding is not None,
        ),
    ),
    Registration(
        kind="lingarr.integration",
        service="lingarr",
        label="arr integration",
        factory=lambda inst: LingarrSettingsProvider(
            inst.base_url,
            inst.api_key,
            inst.integration,
            "lingarr.integration",
            onboarding_managed=inst.onboarding is not None,
        ),
    ),
    Registration(
        kind="lingarr.automation",
        service="lingarr",
        label="automated translation",
        factory=lambda inst: LingarrSettingsProvider(
            inst.base_url,
            inst.api_key,
            inst.automation,
            "lingarr.automation",
            onboarding_managed=inst.onboarding is not None,
        ),
    ),
    Registration(
        kind="lingarr.validation",
        service="lingarr",
        label="subtitle validation",
        factory=lambda inst: LingarrSettingsProvider(
            inst.base_url,
            inst.api_key,
            inst.validation,
            "lingarr.validation",
            onboarding_managed=inst.onboarding is not None,
        ),
    ),  # Cleanuparr: general first, then what the cleaners act on (arr instances and
    # download clients), then the cleaner sections themselves. The sections are
    # full-replace PUTs merged over current (see providers/cleanuparr/sections.py).
    Registration(
        kind="cleanuparr.general",
        service="cleanuparr",
        label="general settings",
        factory=lambda inst: CleanuparrSectionProvider(
            inst.base_url, inst.api_key, inst.general, "cleanuparr.general", "general"
        ),
    ),
    Registration(
        kind="cleanuparr.arr_settings",
        service="cleanuparr",
        label="arr settings",
        factory=lambda inst: CleanuparrArrSettingsProvider(
            inst.base_url, inst.api_key, inst.arr, "cleanuparr.arr_settings"
        ),
    ),
    Registration(
        kind="cleanuparr.arr_instance",
        service="cleanuparr",
        label="arr instances",
        factory=lambda inst: CleanuparrArrInstanceProvider(
            inst.base_url, inst.api_key, inst.arr, "cleanuparr.arr_instance"
        ),
    ),
    Registration(
        kind="cleanuparr.download_client",
        service="cleanuparr",
        label="download clients",
        factory=lambda inst: CleanuparrDownloadClientProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "cleanuparr.download_client",
        ),
    ),
    # Per-client download-cleaner settings, after the clients they belong to.
    Registration(
        kind="cleanuparr.client_settings",
        service="cleanuparr",
        label="download client cleaner settings",
        factory=lambda inst: CleanuparrClientSettingsProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "cleanuparr.client_settings",
        ),
    ),
    Registration(
        kind="cleanuparr.seeding_rule",
        service="cleanuparr",
        label="seeding rules",
        factory=lambda inst: CleanuparrSeedingRuleProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "cleanuparr.seeding_rule",
        ),
    ),
    Registration(
        kind="cleanuparr.queue_cleaner",
        service="cleanuparr",
        label="queue cleaner",
        factory=lambda inst: CleanuparrSectionProvider(
            inst.base_url,
            inst.api_key,
            inst.queue_cleaner,
            "cleanuparr.queue_cleaner",
            "queue_cleaner",
        ),
    ),
    Registration(
        kind="cleanuparr.download_cleaner",
        service="cleanuparr",
        label="download cleaner",
        factory=lambda inst: CleanuparrSectionProvider(
            inst.base_url,
            inst.api_key,
            inst.download_cleaner,
            "cleanuparr.download_cleaner",
            "download_cleaner",
        ),
    ),
    Registration(
        kind="cleanuparr.malware_blocker",
        service="cleanuparr",
        label="malware blocker",
        factory=lambda inst: CleanuparrSectionProvider(
            inst.base_url,
            inst.api_key,
            inst.malware_blocker,
            "cleanuparr.malware_blocker",
            "malware_blocker",
        ),
    ),
    # Kavita: libraries first, so settings can name a library created in the same
    # run (oidc.default_libraries resolves names to ids).
    Registration(
        kind="kavita.library",
        service="kavita",
        label="libraries",
        factory=lambda inst: KavitaLibraryProvider(
            inst.base_url, inst.api_key, inst.libraries, "kavita.library"
        ),
    ),
    Registration(
        kind="kavita.settings",
        service="kavita",
        label="server settings",
        factory=lambda inst: KavitaSettingsProvider(
            inst.base_url, inst.api_key, inst.settings, "kavita.settings"
        ),
    ),
    # Kapowarr: settings first (the download folder must not overlap a root
    # folder, and root folders are checked against it), then root folders, the
    # external download clients and the download-service credentials.
    Registration(
        kind="kapowarr.settings",
        service="kapowarr",
        label="settings",
        factory=lambda inst: KapowarrSettingsProvider(
            inst.base_url, inst.api_key, inst.settings, "kapowarr.settings"
        ),
    ),
    Registration(
        kind="kapowarr.root_folder",
        service="kapowarr",
        label="root folders",
        factory=lambda inst: KapowarrRootFolderProvider(
            inst.base_url, inst.api_key, inst.root_folders, "kapowarr.root_folder"
        ),
    ),
    Registration(
        kind="kapowarr.download_client",
        service="kapowarr",
        label="download clients",
        factory=lambda inst: KapowarrDownloadClientProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "kapowarr.download_client",
        ),
    ),
    Registration(
        kind="kapowarr.credential",
        service="kapowarr",
        label="credentials",
        factory=lambda inst: KapowarrCredentialProvider(
            inst.base_url, inst.api_key, inst.credentials, "kapowarr.credential"
        ),
    ),
    # Tranga: settings, then the file libraries downloads land in, then the
    # connectors that act on finished downloads (library scans, notifications).
    Registration(
        kind="tranga.settings",
        service="tranga",
        label="settings",
        factory=lambda inst: TrangaSettingsProvider(
            inst.base_url, inst.api_key, inst.settings, "tranga.settings"
        ),
    ),
    Registration(
        kind="tranga.file_library",
        service="tranga",
        label="file libraries",
        factory=lambda inst: TrangaFileLibraryProvider(
            inst.base_url, inst.api_key, inst.file_libraries, "tranga.file_library"
        ),
    ),
    Registration(
        kind="tranga.library_connector",
        service="tranga",
        label="library connectors",
        factory=lambda inst: TrangaLibraryConnectorProvider(
            inst.base_url,
            inst.api_key,
            inst.library_connectors,
            "tranga.library_connector",
        ),
    ),
    Registration(
        kind="tranga.notification_connector",
        service="tranga",
        label="notification connectors",
        factory=lambda inst: TrangaNotificationConnectorProvider(
            inst.base_url,
            inst.api_key,
            inst.notification_connectors,
            "tranga.notification_connector",
        ),
    ),
    # Bookshelf (Readarr revival): the shared arr providers on /api/v1, plus the
    # Readarr-only metadata profiles. Custom formats before quality profiles (as for
    # radarr/sonarr), and both profile kinds before root folders, whose defaults
    # reference them by name.
    Registration(
        kind="bookshelf.custom_format",
        service="bookshelf",
        label="custom formats",
        factory=lambda inst: CustomFormatProvider(
            inst.base_url,
            inst.api_key,
            inst.custom_formats,
            "bookshelf.custom_format",
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.quality_profile",
        service="bookshelf",
        label="quality profiles",
        factory=lambda inst: QualityProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.quality_profiles,
            "bookshelf.quality_profile",
            pending_formats=inst.custom_formats or {},
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.metadata_profile",
        service="bookshelf",
        label="metadata profiles",
        factory=lambda inst: MetadataProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.metadata_profiles,
            "bookshelf.metadata_profile",
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.root_folder",
        service="bookshelf",
        label="root folders",
        factory=lambda inst: BookshelfRootFolderProvider(
            inst.base_url,
            inst.api_key,
            inst.root_folders,
            "bookshelf.root_folder",
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.naming",
        service="bookshelf",
        label="naming",
        factory=lambda inst: NamingProvider(
            inst.base_url,
            inst.api_key,
            inst.naming_config,
            "bookshelf.naming",
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.delay_profile",
        service="bookshelf",
        label="delay profiles",
        factory=lambda inst: DelayProfileProvider(
            inst.base_url,
            inst.api_key,
            inst.delay_profiles,
            "bookshelf.delay_profile",
            api_prefix=BOOKSHELF_API,
        ),
    ),
    Registration(
        kind="bookshelf.download_client",
        service="bookshelf",
        label="download clients",
        factory=lambda inst: DownloadClientProvider(
            inst.base_url,
            inst.api_key,
            inst.download_clients,
            "bookshelf.download_client",
            api_prefix=BOOKSHELF_API,
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
    for reg in REGISTRY:
        for inst in getattr(config, reg.service):
            if not in_scope(reg.service, inst.name, service, instance):
                continue
            yield PlannedProvider(
                service=reg.service,
                instance=inst.name,
                label=reg.label,
                provider=reg.factory(inst),
            )
