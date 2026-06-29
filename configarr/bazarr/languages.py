"""Language profile manager for Bazarr using bazarr-py."""

import json
import logging
from typing import Any

import bazarr
import requests
from bazarr.api import SystemLanguagesApi, SystemLanguagesProfilesApi

log = logging.getLogger(__name__)

# Common language name to code mappings
LANGUAGE_CODES = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
    "russian": "ru",
    "arabic": "ar",
    "dutch": "nl",
    "polish": "pl",
    "swedish": "sv",
    "norwegian": "no",
    "danish": "da",
    "finnish": "fi",
    "turkish": "tr",
    "greek": "el",
    "hebrew": "he",
    "thai": "th",
    "vietnamese": "vi",
    "indonesian": "id",
    "hindi": "hi",
}


class LanguageProfileManager:
    """Manages Bazarr language profiles using bazarr-py."""

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
        self.languages_api = SystemLanguagesApi(self.api_client)
        self.profiles_api = SystemLanguagesProfilesApi(self.api_client)

    def get_profiles(self) -> list[dict[str, Any]]:
        """Fetch all existing language profiles."""
        try:
            url = f"{self.base_url}/api/system/languages/profiles"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json() or []
        except Exception as e:
            log.error(f"Failed to get language profiles: {e}", exc_info=True)
            return []

    def get_languages(self) -> list[dict[str, Any]]:
        """Fetch all available languages."""
        try:
            url = f"{self.base_url}/api/system/languages"
            params = {"apikey": self.api_key}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json() or []
        except Exception as e:
            log.error(f"Failed to get languages: {e}", exc_info=True)
            return []

    def find_profile_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a language profile by name."""
        profiles = self.get_profiles()
        for profile in profiles:
            if profile.get("name") == name:
                return profile
        return None

    def get_language_code(self, language_name: str) -> str | None:
        """Get the language code for a language name."""
        # First check our static mapping
        lower_name = language_name.lower()
        if lower_name in LANGUAGE_CODES:
            return LANGUAGE_CODES[lower_name]

        # Then check API
        languages = self.get_languages()
        for lang in languages:
            if lang.get("name", "").lower() == lower_name:
                return lang.get("code2") or lang.get("code3")
        return None

    def _get_next_profile_id(self) -> int:
        """Get the next available profile ID."""
        profiles = self.get_profiles()
        if not profiles:
            return 1
        max_id = max(p.get("profileId", 0) for p in profiles)
        return max_id + 1

    def _build_profile_payload(
        self, profile_id: int, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Build the profile payload for the API."""
        items = []
        languages = config.get("languages", [])
        cutoff_id = None
        cutoff_lang = config.get("cutoff")
        if cutoff_lang:
            cutoff_code = self.get_language_code(cutoff_lang)

        for idx, lang in enumerate(languages, start=1):
            if isinstance(lang, str):
                lang_code = self.get_language_code(lang)
                lang_config = {"language": lang_code}
            else:
                lang_code = self.get_language_code(
                    lang.get("name", lang.get("language", ""))
                )
                lang_config = {
                    "language": lang_code,
                    "hi": str(lang.get("hi", False)),
                    "forced": str(lang.get("forced", False)),
                    "audio_exclude": str(lang.get("audio_exclude", False)),
                }

            if lang_code:
                items.append(
                    {
                        "id": idx,
                        "language": lang_code,
                        "audio_exclude": lang_config.get("audio_exclude", "False"),
                        "hi": lang_config.get("hi", "False"),
                        "forced": lang_config.get("forced", "False"),
                    }
                )
                # Check if this is the cutoff language
                if cutoff_lang and lang_code == cutoff_code:
                    cutoff_id = idx

        return {
            "profileId": profile_id,
            "name": config.get("name"),
            "items": items,
            "cutoff": cutoff_id,
            "mustContain": config.get("must_contain", []),
            "mustNotContain": config.get("must_not_contain", []),
            "originalFormat": config.get("original_format"),
        }

    def _save_profiles(self, profiles: list[dict[str, Any]]) -> bool:
        """Save profiles via POST to /api/system/settings."""
        if self.dry_run:
            log.debug(f"[DRY RUN] Would save profiles: {profiles}")
            return True

        try:
            url = f"{self.base_url}/api/system/settings"
            params = {"apikey": self.api_key}
            files = {"languages-profiles": (None, json.dumps(profiles))}

            resp = requests.post(url, params=params, files=files, timeout=30)
            resp.raise_for_status()
            return True
        except Exception as e:
            log.error(f"Failed to save profiles: {e}", exc_info=True)
            return False

    def sync_profiles(
        self, profiles_config: list[dict[str, Any]]
    ) -> tuple[list[str], list[str], bool]:
        """Sync language profiles.

        Listed profiles are written from config: ones already on the server are
        overwritten, new ones are created, and profiles absent from config are
        preserved. All profiles are written in a single batch POST, so the save
        either succeeds or fails as a whole.

        Returns:
            Tuple of (created_names, updated_names, saved_ok).
        """
        created: list[str] = []
        updated: list[str] = []

        # Get existing profiles
        existing_profiles = self.get_profiles()
        existing_by_name = {p.get("name"): p for p in existing_profiles}
        config_names = {p.get("name", "Unknown") for p in profiles_config}

        # Build the complete list of profiles to save
        all_profiles = []
        next_id = self._get_next_profile_id()

        for profile_config in profiles_config:
            name = profile_config.get("name", "Unknown")
            existing = existing_by_name.get(name)

            if existing:
                # Overwrite the existing profile with config-derived values
                profile_id = existing.get("profileId", next_id)
                all_profiles.append(
                    self._build_profile_payload(int(profile_id), profile_config)
                )
                updated.append(name)
            else:
                all_profiles.append(
                    self._build_profile_payload(next_id, profile_config)
                )
                next_id += 1
                created.append(name)

        # Include existing profiles not in config (preserve them)
        for name, existing in existing_by_name.items():
            if name not in config_names:
                all_profiles.append(existing)

        # Single batch save — all-or-nothing.
        saved_ok = True
        if profiles_config:
            saved_ok = self._save_profiles(all_profiles)

        return created, updated, saved_ok
