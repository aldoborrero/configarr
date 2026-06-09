"""Bazarr managers for configarr."""

import logging
from typing import Any

import bazarr
import requests
from bazarr.api import SystemLanguagesApi, SystemLanguagesProfilesApi, SystemSettingsApi
from bazarr.models import SystemSettingsUpdate

from configarr.bazarr.languages import LanguageProfileManager

log = logging.getLogger(__name__)

# Map configarr provider names to Bazarr provider names
PROVIDER_NAME_MAP = {
    "submate": "whisperai",
    "opensubtitlescom": "opensubtitlescom",
    "opensubtitles": "opensubtitles",
    "addic7ed": "addic7ed",
    "podnapisi": "podnapisi",
    "subdivx": "subdivx",
}


class BazarrClient:
    """Unified Bazarr API client using bazarr-py."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        dry_run: bool = False,
        verbose: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.dry_run = dry_run
        self.verbose = verbose

        config = bazarr.Configuration(host=base_url)
        config.api_key["apikey"] = api_key
        self.api_client = bazarr.ApiClient(config)

        # API instances
        self.settings_api = SystemSettingsApi(self.api_client)
        self.languages_api = SystemLanguagesApi(self.api_client)
        self.profiles_api = SystemLanguagesProfilesApi(self.api_client)

        # Language profile manager (uses requests directly for better API support)
        self._language_manager = LanguageProfileManager(base_url, api_key, dry_run, verbose)

    # Settings methods
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

    def _sync_settings_section(self, section: str, config: dict[str, Any]) -> bool:
        """Sync a settings section using direct API calls."""
        if self.dry_run:
            log.debug(f"[DRY RUN] Would update {section} settings: {config}")
            return True

        try:
            url = f"{self.base_url}/api/system/settings"
            params = {"apikey": self.api_key}

            # Build form data: settings-{section}-{field}=value
            files = {}
            for field, value in config.items():
                key = f"settings-{section}-{field}"
                # Handle booleans and other types
                if isinstance(value, bool):
                    files[key] = (None, str(value).lower())
                else:
                    files[key] = (None, str(value))

            resp = requests.post(url, params=params, files=files, timeout=60)
            resp.raise_for_status()
            return True
        except Exception as e:
            log.error(f"Failed to update {section} settings: {e}")
            return False

    def sync_general(self, config: dict[str, Any]) -> bool:
        """Sync general settings."""
        return self._sync_settings_section("general", config)

    def sync_sonarr(self, config: dict[str, Any]) -> bool:
        """Sync Sonarr connection settings."""
        return self._sync_settings_section("sonarr", config)

    def sync_radarr(self, config: dict[str, Any]) -> bool:
        """Sync Radarr connection settings."""
        return self._sync_settings_section("radarr", config)

    def sync_provider(self, provider_name: str, config: dict[str, Any]) -> bool:
        """Sync a subtitle provider's settings and enable it."""
        # Map config name to Bazarr internal name
        bazarr_name = PROVIDER_NAME_MAP.get(provider_name, provider_name)

        if self.dry_run:
            log.debug(f"[DRY RUN] Would configure provider {bazarr_name}: {config}")
            return True

        try:
            # Get current settings to check enabled_providers
            url = f"{self.base_url}/api/system/settings"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            current = resp.json()

            # Get current enabled providers (should be a list of strings)
            enabled_raw = current.get("general", {}).get("enabled_providers", [])

            # Normalize to a clean list of provider names
            enabled: list[str] = []
            if isinstance(enabled_raw, list):
                for item in enabled_raw:
                    if isinstance(item, str) and not item.startswith("["):
                        # Clean string, add it
                        enabled.append(item)
                    # Skip malformed entries (JSON strings, nested arrays)

            # Add provider to enabled list if not already there
            if bazarr_name not in enabled:
                enabled.append(bazarr_name)

            # Build form data for POST - each setting is a separate field
            # Format: settings-{provider}-{field}=value
            # enabled_providers expects comma-separated string, not JSON
            files = {
                "settings-general-enabled_providers": (None, ",".join(enabled)),
            }
            for field, value in config.items():
                key = f"settings-{bazarr_name}-{field}"
                if isinstance(value, bool):
                    files[key] = (None, str(value).lower())
                else:
                    files[key] = (None, str(value))

            resp = requests.post(url, params=params, files=files, timeout=60)
            resp.raise_for_status()
            return True
        except Exception as e:
            log.error(f"Failed to sync provider {provider_name}: {e}")
            return False

    # Language profile methods (delegated to LanguageProfileManager)
    def get_language_profiles(self) -> list[dict[str, Any]]:
        """Fetch all existing language profiles."""
        return self._language_manager.get_profiles()

    def get_languages(self) -> list[dict[str, Any]]:
        """Fetch all available languages."""
        return self._language_manager.get_languages()

    def find_profile_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a language profile by name."""
        return self._language_manager.find_profile_by_name(name)

    def sync_language_profiles(
        self, profiles_config: list[dict[str, Any]]
    ) -> tuple[list[str], list[str], bool]:
        """Sync language profiles.

        Returns:
            Tuple of (created_names, updated_names, saved_ok).
        """
        return self._language_manager.sync_profiles(profiles_config)


__all__ = [
    "BazarrClient",
    "LanguageProfileManager",
]
