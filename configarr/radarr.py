"""Radarr API client using radarr-py."""

import logging
from typing import Any

import radarr
from radarr.api import (
    CustomFormatApi,
    DelayProfileApi,
    DownloadClientApi,
    LanguageApi,
    NamingConfigApi,
    NotificationApi,
    QualityDefinitionApi,
    QualityProfileApi,
    RootFolderApi,
)
from radarr.models import (
    ContractField,
    CustomFormatResource,
    CustomFormatSpecificationSchema,
    DelayProfileResource,
    DownloadClientResource,
    Language,
    NamingConfigResource,
    NotificationResource,
    QualityDefinitionResource,
    QualityProfileQualityItemResource,
    QualityProfileResource,
    RootFolderResource,
)

from configarr.models import SyncStatus

log = logging.getLogger(__name__)

# Colon replacement format mapping
COLON_REPLACEMENT_MAP = {
    "delete": "delete",
    "dash": "dash",
    "spaceDash": "spaceDash",
    "spaceDashSpace": "spaceDashSpace",
    "smart": "smart",
}


class RadarrClient:
    """Radarr API client using radarr-py."""

    def __init__(self, base_url: str, api_key: str):
        config = radarr.Configuration(host=base_url)
        config.api_key["X-Api-Key"] = api_key
        self.api_client = radarr.ApiClient(config)

        # API instances
        self.custom_formats = CustomFormatApi(self.api_client)
        self.quality_profiles = QualityProfileApi(self.api_client)
        self.naming_config = NamingConfigApi(self.api_client)
        self.delay_profiles = DelayProfileApi(self.api_client)
        self.quality_definitions = QualityDefinitionApi(self.api_client)
        self.languages = LanguageApi(self.api_client)
        self.root_folders = RootFolderApi(self.api_client)
        self.download_clients = DownloadClientApi(self.api_client)
        self.notifications = NotificationApi(self.api_client)

        # Caches
        self._quality_defs: list[QualityDefinitionResource] | None = None
        self._download_client_schemas: dict[str, DownloadClientResource] | None = None
        self._notification_schemas: dict[str, NotificationResource] | None = None
        self._custom_format_ids: dict[str, int] = {}

    def _find_by_name[T](self, resources: list[T], name: str) -> T | None:
        """Find resource by name in list."""
        for r in resources:
            if hasattr(r, "name") and r.name == name:
                return r
        return None

    def _find_by_path[T](self, resources: list[T], path: str) -> T | None:
        """Find resource by path in list."""
        for r in resources:
            if hasattr(r, "path") and r.path == path:
                return r
        return None

    # Quality Definitions
    def get_quality_definitions(self) -> list[QualityDefinitionResource]:
        """Get quality definitions (cached)."""
        if self._quality_defs is None:
            self._quality_defs = self.quality_definitions.list_quality_definition()
        return self._quality_defs

    def sync_quality_definitions(self, config: dict[str, Any]) -> SyncStatus:
        """Sync quality definitions. Updates min/max sizes."""
        definitions = self.get_quality_definitions()

        for quality_def in definitions:
            quality_name = quality_def.quality.name if quality_def.quality else None
            if quality_name and quality_name in config:
                quality_config = config[quality_name]
                if "min" in quality_config:
                    quality_def.min_size = quality_config["min"]
                if "max" in quality_config:
                    quality_def.max_size = quality_config["max"]
                if "preferred" in quality_config:
                    quality_def.preferred_size = quality_config["preferred"]

        # Update all definitions
        self.quality_definitions.put_quality_definition_update(
            quality_definition_resource=definitions
        )
        log.debug("Updated quality definitions")
        return SyncStatus.UPDATED

    # Root Folders
    def sync_root_folder(self, path: str) -> SyncStatus:
        """Sync a root folder. Creates if not exists."""
        existing = self.root_folders.list_root_folder()
        found = self._find_by_path(existing, path)

        if found:
            log.debug(f"Root folder exists: {path}")
            return SyncStatus.UNCHANGED

        resource = RootFolderResource(path=path)
        self.root_folders.create_root_folder(root_folder_resource=resource)
        log.debug(f"Created root folder: {path}")
        return SyncStatus.CREATED

    # Naming Configuration
    def sync_naming_config(self, config: dict[str, Any]) -> SyncStatus:
        """Sync naming configuration."""
        current = self.naming_config.get_naming_config()

        colon_replacement = config.get("colon_replacement", "smart")
        colon_format = COLON_REPLACEMENT_MAP.get(colon_replacement, "smart")

        # Build updated config
        updated = NamingConfigResource(
            id=current.id,
            rename_movies=config.get("rename_movies", True),
            replace_illegal_characters=config.get("replace_illegal_characters", True),
            colon_replacement_format=colon_format,
            standard_movie_format=config.get(
                "standard_movie_format", current.standard_movie_format
            ),
            movie_folder_format=config.get(
                "movie_folder_format", current.movie_folder_format
            ),
        )

        self.naming_config.update_naming_config(
            str(current.id), naming_config_resource=updated
        )
        log.debug("Updated naming configuration")
        return SyncStatus.UPDATED

    # Delay Profiles
    def _find_delay_profile_by_settings(
        self, profiles: list[DelayProfileResource], config: dict[str, Any]
    ) -> DelayProfileResource | None:
        """Find delay profile by matching settings."""
        for p in profiles:
            if (
                p.usenet_delay == config.get("usenet_delay", 0)
                and p.torrent_delay == config.get("torrent_delay", 0)
                and p.preferred_protocol == config.get("preferred_protocol", "torrent")
            ):
                return p
        return None

    def sync_delay_profile(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a delay profile."""
        existing = self.delay_profiles.list_delay_profile()
        found = self._find_delay_profile_by_settings(existing, config)

        if found:
            log.debug(f"Delay profile exists: {name}")
            return SyncStatus.UNCHANGED

        bypass_score = config.get("bypass_if_above_custom_format_score", 0)

        resource = DelayProfileResource(
            enable_usenet=config.get("enable_usenet", True),
            enable_torrent=config.get("enable_torrent", True),
            preferred_protocol=config.get("preferred_protocol", "torrent"),
            usenet_delay=config.get("usenet_delay", 0),
            torrent_delay=config.get("torrent_delay", 0),
            bypass_if_highest_quality=config.get("bypass_if_highest_quality", True),
            bypass_if_above_custom_format_score=bypass_score > 0,
            minimum_custom_format_score=config.get("minimum_custom_format_score", 0),
            order=2147483647,
            tags=config.get("tags", []),
        )

        self.delay_profiles.create_delay_profile(delay_profile_resource=resource)
        log.debug(f"Created delay profile: {name}")
        return SyncStatus.CREATED

    # Custom Formats
    def get_custom_format_ids(self) -> dict[str, int]:
        """Get mapping of custom format name → ID (cached)."""
        if not self._custom_format_ids:
            existing = self.custom_formats.list_custom_format()
            self._custom_format_ids = {cf.name: cf.id for cf in existing if cf.name and cf.id}
        return self._custom_format_ids

    def sync_custom_format(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a custom format. Creates or updates."""
        existing = self.custom_formats.list_custom_format()
        found = self._find_by_name(existing, name)

        specs = []
        for spec_config in config.get("specifications", []):
            fields = []
            for field_name, field_value in spec_config.get("fields", {}).items():
                fields.append(ContractField(name=field_name, value=field_value))

            specs.append(CustomFormatSpecificationSchema(
                name=spec_config["name"],
                implementation=spec_config["implementation"],
                negate=spec_config.get("negate", False),
                required=spec_config.get("required", True),
                fields=fields,
            ))

        resource = CustomFormatResource(
            name=name,
            include_custom_format_when_renaming=config.get("include_when_renaming", False),
            specifications=specs,
        )

        if found:
            resource.id = found.id
            self.custom_formats.update_custom_format(str(found.id), custom_format_resource=resource)
            self._custom_format_ids[name] = found.id
            log.debug(f"Updated custom format: {name}")
            return SyncStatus.UPDATED

        result = self.custom_formats.create_custom_format(custom_format_resource=resource)
        self._custom_format_ids[name] = result.id
        log.debug(f"Created custom format: {name}")
        return SyncStatus.CREATED

    # Quality Profiles
    def _resolve_language(self, name: str) -> Language | None:
        """Resolve a language name (e.g. 'Original', 'Any', 'English') to a Language.

        Returns None if the name cannot be matched, in which case the caller
        leaves the profile's language untouched.
        """
        if not hasattr(self, "_language_cache"):
            self._language_cache = self.languages.list_language()
        for lang in self._language_cache:
            if lang.name and lang.name.lower() == name.lower():
                return Language(id=lang.id, name=lang.name)
        log.warning(f"Language '{name}' not found, leaving quality profile language unset")
        return None

    def sync_quality_profile(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a quality profile. Creates or updates."""
        existing = self.quality_profiles.list_quality_profile()
        found = self._find_by_name(existing, name)

        # Get quality definitions to build items
        quality_defs = self.get_quality_definitions()
        qualities_config = config.get("qualities", [])

        # Build enabled quality names set
        enabled_names = set()
        for q in qualities_config:
            q_name = q.get("name") if isinstance(q, dict) else q
            if isinstance(q, dict) and q.get("enabled", True):
                enabled_names.add(q_name)
                if "qualities" in q:
                    for nested in q["qualities"]:
                        enabled_names.add(nested)
            elif isinstance(q, str):
                enabled_names.add(q)

        # Find cutoff quality ID
        cutoff_name = config.get("upgrade", {}).get("until_quality", "WEBDL-1080p")
        cutoff_id = None
        for qd in quality_defs:
            if qd.quality and qd.quality.name == cutoff_name:
                cutoff_id = qd.quality.id
                break

        if cutoff_id is None:
            for qd in quality_defs:
                if qd.quality and qd.quality.name in enabled_names:
                    cutoff_id = qd.quality.id
                    break

        if cutoff_id is None:
            cutoff_id = 3

        # Build quality items
        items = []
        for qd in quality_defs:
            if qd.quality:
                items.append(
                    QualityProfileQualityItemResource(
                        quality=qd.quality,
                        items=[],
                        allowed=qd.quality.name in enabled_names,
                    )
                )

        # Build format items from custom_format_scores
        format_items = []
        cf_scores = config.get("custom_format_scores", {})
        if cf_scores:
            cf_ids = self.get_custom_format_ids()
            for cf_name, score in cf_scores.items():
                cf_id = cf_ids.get(cf_name)
                if cf_id is not None:
                    format_items.append({"format": cf_id, "name": cf_name, "score": score})
                else:
                    log.warning(f"Custom format '{cf_name}' not found, skipping score assignment")

        upgrade_config = config.get("upgrade", {})

        resource = QualityProfileResource(
            name=name,
            upgrade_allowed=upgrade_config.get("allowed", True),
            cutoff=cutoff_id,
            items=items,
            min_format_score=config.get("min_format_score", 0),
            cutoff_format_score=upgrade_config.get("until_score", 10000),
            min_upgrade_format_score=1,
            format_items=format_items,
        )

        # Radarr quality profiles carry a language filter. When unset it is
        # serialized as null, which makes Radarr reject every release with
        # "<blank> is wanted, but found <lang>". Resolve the configured language
        # (e.g. "Any" to never reject, "Original" for the release's own language).
        language_name = config.get("language")
        if language_name:
            language = self._resolve_language(language_name)
            if language:
                resource.language = language

        if found:
            resource.id = found.id
            self.quality_profiles.update_quality_profile(str(found.id), quality_profile_resource=resource)
            log.debug(f"Updated quality profile: {name}")
            return SyncStatus.UPDATED

        self.quality_profiles.create_quality_profile(
            quality_profile_resource=resource
        )
        log.debug(f"Created quality profile: {name}")
        return SyncStatus.CREATED

    # Download Clients
    def get_download_client_schema(
        self, implementation: str
    ) -> DownloadClientResource | None:
        """Get schema for download client implementation (cached)."""
        if self._download_client_schemas is None:
            schemas = self.download_clients.list_download_client_schema()
            self._download_client_schemas = {
                s.implementation: s for s in schemas if s.implementation
            }
        return self._download_client_schemas.get(implementation)

    def _build_fields(
        self, schema_fields: list | None, settings: dict[str, Any]
    ) -> list:
        """Build fields list from schema and settings."""
        from radarr.models import ContractField

        fields = []
        for sf in schema_fields or []:
            field = ContractField(name=sf.name)
            if sf.name in settings:
                field.value = settings[sf.name]
            elif sf.value is not None:
                field.value = sf.value
            fields.append(field)
        return fields

    def sync_download_client(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a download client."""
        implementation = config.get("implementation")
        if not implementation:
            raise ValueError(f"Missing 'implementation' for download client: {name}")

        schema = self.get_download_client_schema(implementation)
        if not schema:
            raise ValueError(f"Unknown implementation: {implementation}")

        existing = self.download_clients.list_download_client()
        found = self._find_by_name(existing, name)

        settings = config.get("settings", {})

        if found:
            # Update existing - modify in place
            found.name = name
            found.enable = config.get("enable", True)
            found.priority = config.get("priority", 1)
            found.tags = config.get("tags", [])
            if found.fields:
                for field in found.fields:
                    if field.name in settings:
                        field.value = settings[field.name]
            self.download_clients.update_download_client(
                found.id, download_client_resource=found
            )
            log.debug(f"Updated download client: {name}")
            return SyncStatus.UPDATED

        # Create new
        resource = DownloadClientResource(
            name=name,
            implementation=implementation,
            config_contract=schema.config_contract,
            protocol=schema.protocol,
            enable=config.get("enable", True),
            priority=config.get("priority", 1),
            fields=self._build_fields(schema.fields, settings),
            tags=config.get("tags", []),
        )

        self.download_clients.create_download_client(
            download_client_resource=resource
        )
        log.debug(f"Created download client: {name}")
        return SyncStatus.CREATED

    # Notifications (Connections)
    def get_notification_schema(self, implementation: str) -> NotificationResource | None:
        """Get schema for notification implementation (cached)."""
        if self._notification_schemas is None:
            schemas = self.notifications.list_notification_schema()
            self._notification_schemas = {
                s.implementation: s for s in schemas if s.implementation
            }
        return self._notification_schemas.get(implementation)

    def sync_notification(self, name: str, config: dict[str, Any]) -> SyncStatus:
        """Sync a notification/connection."""
        implementation = config.get("implementation")
        if not implementation:
            raise ValueError(f"Missing 'implementation' for notification: {name}")

        schema = self.get_notification_schema(implementation)
        if not schema:
            raise ValueError(f"Unknown notification implementation: {implementation}")

        existing = self.notifications.list_notification()
        found = self._find_by_name(existing, name)

        settings = config.get("settings", {})
        on_download = config.get("on_download", True)
        on_upgrade = config.get("on_upgrade", True)
        on_rename = config.get("on_rename", True)

        if found:
            found.name = name
            found.on_download = on_download
            found.on_upgrade = on_upgrade
            found.on_rename = on_rename
            if found.fields:
                for field in found.fields:
                    if field.name in settings:
                        field.value = settings[field.name]
            self.notifications.update_notification(
                int(found.id), notification_resource=found
            )
            log.debug(f"Updated notification: {name}")
            return SyncStatus.UPDATED

        resource = NotificationResource(
            name=name,
            implementation=implementation,
            config_contract=schema.config_contract,
            on_download=on_download,
            on_upgrade=on_upgrade,
            on_rename=on_rename,
            fields=self._build_fields(schema.fields, settings),
            tags=config.get("tags", []),
        )

        self.notifications.create_notification(
            notification_resource=resource
        )
        log.debug(f"Created notification: {name}")
        return SyncStatus.CREATED
