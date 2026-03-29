"""Settings manager for Bazarr using bazarr-py."""

import logging
from typing import Any

import bazarr
from bazarr.api import SystemSettingsApi
from bazarr.models import (
    GeneralSettings,
    RadarrSettings,
    SonarrSettings,
    SystemSettingsUpdate,
)

log = logging.getLogger(__name__)


class SettingsManager:
    """Manages Bazarr settings using bazarr-py."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self.verbose = verbose

        config = bazarr.Configuration(host=base_url)
        config.api_key["apikey"] = api_key
        self.api_client = bazarr.ApiClient(config)
        self.settings_api = SystemSettingsApi(self.api_client)

    def get_settings(self) -> dict[str, Any] | None:
        """Fetch all current settings."""
        try:
            settings = self.settings_api.get_system_settings()
            return settings.to_dict() if settings else None
        except Exception as e:
            log.error(f"Failed to get settings: {e}")
            return None

    def update_settings(self, settings: dict[str, Any]) -> bool:
        """Update settings via POST."""
        if self.dry_run:
            log.debug(f"[DRY RUN] Would update settings: {settings}")
            return True

        try:
            update = SystemSettingsUpdate.from_dict(settings)
            self.settings_api.post_system_settings(update)
            return True
        except Exception as e:
            log.error(f"Failed to update settings: {e}")
            return False

    def sync_general(self, config: dict[str, Any]) -> bool:
        """Sync general settings."""
        current = self.get_settings()
        if not current:
            return False

        general_settings = GeneralSettings.from_dict(config)
        payload = SystemSettingsUpdate(general=general_settings)

        if self.dry_run:
            log.debug(f"[DRY RUN] Would update general settings: {config}")
            return True

        try:
            self.settings_api.post_system_settings(payload)
            return True
        except Exception as e:
            log.error(f"Failed to update general settings: {e}")
            return False

    def sync_sonarr(self, config: dict[str, Any]) -> bool:
        """Sync Sonarr connection settings."""
        sonarr_settings = SonarrSettings.from_dict(config)
        payload = SystemSettingsUpdate(sonarr=sonarr_settings)

        if self.dry_run:
            log.debug(f"[DRY RUN] Would update sonarr settings: {config}")
            return True

        try:
            self.settings_api.post_system_settings(payload)
            return True
        except Exception as e:
            log.error(f"Failed to update sonarr settings: {e}")
            return False

    def sync_radarr(self, config: dict[str, Any]) -> bool:
        """Sync Radarr connection settings."""
        radarr_settings = RadarrSettings.from_dict(config)
        payload = SystemSettingsUpdate(radarr=radarr_settings)

        if self.dry_run:
            log.debug(f"[DRY RUN] Would update radarr settings: {config}")
            return True

        try:
            self.settings_api.post_system_settings(payload)
            return True
        except Exception as e:
            log.error(f"Failed to update radarr settings: {e}")
            return False

    def sync_provider(self, provider_name: str, config: dict[str, Any]) -> bool:
        """Sync a subtitle provider's settings."""
        payload = {provider_name: config}
        return self.update_settings(payload)
