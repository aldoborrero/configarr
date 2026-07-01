"""Bazarr language-profile provider (rollout work-list #17). Client-free: talks
HTTP via requests.

Language profiles listed in config are rebuilt and overwrite the server copy,
matched by profile ``name``; profiles only on the server are preserved. Each
configured language resolves by name → ISO code (a static table first, then
``GET /api/system/languages``); names that resolve to nothing are dropped. The
``cutoff`` names one of the *listed* languages and is stored as that language's
item id (or ``None`` when the cutoff is not among the listed languages).

The read API (``GET /api/system/languages/profiles``) and the write API
(form-POST ``languages-profiles`` to ``/api/system/settings``) differ, and the
write is a batch that replaces the whole profiles document. This provider keeps
the per-resource contract by re-reading the live profiles in ``apply()`` and
writing the rewritten profile alongside every other server profile, so a managed
profile overwrites its server copy while unmanaged profiles stay intact.
"""

from __future__ import annotations

import json
from collections.abc import Hashable
from typing import Any

import requests

from configarr.build import merge_full_replace
from configarr.model import Op, ResourcePlan
from configarr.normalize import coerce_scalar
from configarr.providers.base import Action, CurrentStateCache

# Common language name → ISO code, consulted before the server's language list so a
# plan resolves the everyday languages without a second fetch (mirrors the legacy
# LanguageProfileManager table).
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


def _canonicalize(value: Any) -> Any:
    """Recursively coerce scalars so the built profile and the server profile (which
    may echo bools as ``"False"`` strings and ids as strings) compare equal."""
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    return coerce_scalar(value)


class BazarrLanguageProfileProvider(CurrentStateCache):
    """Diffs Bazarr language profiles by name (full-replace)."""

    # The batch POST replaces the whole profile, so a re-plan must surface any server
    # key the built payload would drop; merge_full_replace keeps those keys quiet for
    # an existing profile.
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or []
        self._session = requests.Session()
        self._languages_cache: list[dict[str, Any]] | None = None

    def _profiles_url(self) -> str:
        return f"{self.base_url}/api/system/languages/profiles"

    def _languages_url(self) -> str:
        return f"{self.base_url}/api/system/languages"

    def _settings_url(self) -> str:
        return f"{self.base_url}/api/system/settings"

    def _get_profiles(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._profiles_url(), params={"apikey": self.api_key})
        resp.raise_for_status()
        return resp.json() or []

    def _languages(self) -> list[dict[str, Any]]:
        if self._languages_cache is None:
            resp = self._session.get(
                self._languages_url(), params={"apikey": self.api_key}
            )
            resp.raise_for_status()
            self._languages_cache = resp.json() or []
        return self._languages_cache

    def _language_code(self, language_name: str) -> str | None:
        lower = language_name.lower()
        if lower in LANGUAGE_CODES:
            return LANGUAGE_CODES[lower]
        for lang in self._languages():
            if (lang.get("name") or "").lower() == lower:
                return lang.get("code2") or lang.get("code3")
        return None

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return self._get_profiles()

    @staticmethod
    def _lang_name(lang: Any) -> str:
        if isinstance(lang, str):
            return lang
        return lang.get("name") or lang.get("language") or ""

    def _build_profile(
        self, profile_id: int, profile_config: dict[str, Any]
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        cutoff_id: int | None = None
        cutoff_name = profile_config.get("cutoff")
        cutoff_code = self._language_code(cutoff_name) if cutoff_name else None

        for lang in profile_config.get("languages", []):
            code = self._language_code(self._lang_name(lang))
            if not code:
                continue
            flags = lang if isinstance(lang, dict) else {}
            item_id = len(items) + 1
            items.append(
                {
                    "id": item_id,
                    "language": code,
                    "audio_exclude": str(flags.get("audio_exclude", False)),
                    "hi": str(flags.get("hi", False)),
                    "forced": str(flags.get("forced", False)),
                    # Bazarr stores this on every item; emit it (default False) so
                    # the full-replace write doesn't drop it and diff forever.
                    "audio_only_include": str(flags.get("audio_only_include", False)),
                }
            )
            # The cutoff must name one of the listed languages; record its item id.
            if cutoff_code and code == cutoff_code and cutoff_id is None:
                cutoff_id = item_id

        return {
            "profileId": profile_id,
            "name": profile_config.get("name"),
            "items": items,
            "cutoff": cutoff_id,
            "mustContain": profile_config.get("must_contain", []),
            "mustNotContain": profile_config.get("must_not_contain", []),
            "originalFormat": profile_config.get("original_format"),
        }

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current = self.fetch_current()
        current_by_name = {p.get("name"): p for p in current}
        next_id = (max((p.get("profileId", 0) for p in current), default=0)) + 1

        desired: list[dict[str, Any]] = []
        for profile_config in self.config:
            name = profile_config.get("name")
            existing = current_by_name.get(name)
            if existing is not None:
                profile_id = int(existing.get("profileId", next_id))
            else:
                profile_id = next_id
                next_id += 1
            built = self._build_profile(profile_id, profile_config)
            if existing is not None:
                built = merge_full_replace({}, existing, built)
            desired.append(built)
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = _canonicalize(resource)
        return result

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op not in (Op.CREATE, Op.UPDATE):
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        # Re-read the live profiles so unmanaged profiles (and profiles written by
        # earlier actions) survive; replace only the one this action manages.
        others = [p for p in self._get_profiles() if p.get("name") != action.key]
        all_profiles = [*others, dict(action.payload)]
        files = {"languages-profiles": (None, json.dumps(all_profiles))}
        resp = self._session.post(
            self._settings_url(), params={"apikey": self.api_key}, files=files
        )
        resp.raise_for_status()
        self.invalidate_current()
