"""Lingarr settings provider. Client-free: talks HTTP via requests.

Lingarr keeps all settings as one flat ``key -> value`` store (no per-object id or
name), read via ``POST /api/setting/multiple/get`` (a JSON list of keys) and written
via ``POST /api/setting/multiple/set`` (a JSON ``{key: value}`` map of strings). This
provider owns one logical group of that store — ``lingarr.translation``,
``lingarr.integration`` or ``lingarr.automation`` — as a singleton (``match_key``
is a fixed sentinel, the only op is UPDATE).

It is an over-current provider: build_desired emits only the keys the user set (that
Lingarr knows), and the diff compares those against their current values, so every
other Lingarr setting stays untouched. A configured key outside the group's known set
is warned about and dropped rather than written blindly (Lingarr ignores unknown keys
silently, which would otherwise no-op without a trace).

Auth: with ``AUTH_ENABLED=false`` the settings API needs no credential, but it 403s
until onboarding has run once — surfaced as a clear error rather than self-healed, so
a plan stays read-only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

from configarr.normalize import coerce_scalar, redact_secret_fields
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.transport import build_session

if TYPE_CHECKING:
    import requests

log = logging.getLogger(__name__)

# Known setting keys per group (from Lingarr's SettingKeys). Used to validate the
# configured keys — a key outside its group's set is a typo or belongs elsewhere.
INTEGRATION_KEYS: frozenset[str] = frozenset(
    {
        "radarr_url",
        "radarr_api_key",
        "radarr_default_include",
        "radarr_settings_completed",
        "sonarr_url",
        "sonarr_api_key",
        "sonarr_default_include",
        "sonarr_settings_completed",
    }
)
# Translation covers service selection, every backend's model/key/template, and the
# shared prompt/batch/retry knobs.
TRANSLATION_KEYS: frozenset[str] = frozenset(
    {
        "service_type",
        "openai_model",
        "openai_api_key",
        "openai_request_template",
        "anthropic_model",
        "anthropic_api_key",
        "anthropic_version",
        "anthropic_request_template",
        "local_ai_model",
        "local_ai_endpoint",
        "local_ai_api_key",
        "local_ai_chat_request_template",
        "local_ai_generate_request_template",
        "deepl_api_key",
        "gemini_model",
        "gemini_api_key",
        "gemini_request_template",
        "deepseek_model",
        "deepseek_api_key",
        "deepseek_request_template",
        "mistral_model",
        "mistral_api_key",
        "mistral_request_template",
        "xai_model",
        "xai_api_key",
        "xai_request_template",
        "libretranslate_url",
        "libretranslate_api_key",
        "source_languages",
        "target_languages",
        "ai_prompt",
        "ai_user_prompt",
        "proofread_prompt",
        "proofread_user_prompt",
        "ai_context_before",
        "ai_context_after",
        "ai_context_use_translated",
        "fix_overlapping_subtitles",
        "strip_subtitle_formatting",
        "preserve_line_breaks",
        "add_translator_info",
        "use_batch_translation",
        "max_batch_size",
        "use_subtitle_tagging",
        "remove_language_tag",
        "subtitle_tag",
        "ignore_captions",
        "request_timeout",
        "max_retries",
        "retry_delay",
        "retry_delay_multiplier",
        "navigate_to_details_on_request",
        "language_code_format",
    }
)

# Scheduled file-mode translation (Lingarr's AutomatedTranslationJob): whether it
# runs, its cron, the per-run cap, and the per-type schedules/age thresholds.
AUTOMATION_KEYS: frozenset[str] = frozenset(
    {
        "automation_enabled",
        "translation_schedule",
        "max_translations_per_run",
        "translation_cycle",
        "movie_schedule",
        "show_schedule",
        "movie_age_threshold",
        "show_age_threshold",
    }
)

# Subtitle sanity checks Lingarr applies before translating a file.
VALIDATION_KEYS: frozenset[str] = frozenset(
    {
        "subtitle_validation_enabled",
        "subtitle_validation_maxfilesizebytes",
        "subtitle_validation_maxsubtitlelength",
        "subtitle_validation_minsubtitlelength",
        "subtitle_validation_mindurationms",
        "subtitle_validation_maxdurationsecs",
    }
)

_KNOWN_KEYS = {
    "lingarr.translation": TRANSLATION_KEYS,
    "lingarr.integration": INTEGRATION_KEYS,
    "lingarr.automation": AUTOMATION_KEYS,
    "lingarr.validation": VALIDATION_KEYS,
}
_SINGLETON = "settings"


def lingarr_session(api_key: str) -> requests.Session:
    """A session that authenticates the way Lingarr's LingarrAuthorize expects
    (``X-Api-Key``) whenever a key is configured. With ``AUTH_ENABLED=false`` no
    key is needed and none is sent."""
    session = build_session()
    if api_key:
        session.headers["X-Api-Key"] = api_key
    return session


def _encode(value: Any) -> str:
    """Encode a value for Lingarr's string-typed set API: bools as ``true``/``false``,
    lists/dicts as compact JSON (Lingarr stores e.g. ``source_languages`` as a JSON
    array with no spaces), everything else stringified."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _canonicalize(value: Any) -> Any:
    """Canonicalize a setting value for comparison. A JSON-container string (a Lingarr
    array/object setting such as ``source_languages``) is parsed to its object so
    whitespace or key-order differences between our encoding and Lingarr's serializer
    don't produce a phantom diff; scalars fall through to ``coerce_scalar``."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                return json.loads(stripped)
            except ValueError:
                pass
    return coerce_scalar(value)


class LingarrSettingsProvider(CurrentStateCache):
    """Diffs one group of Lingarr's flat settings store (singleton, UPDATE-only)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: Any,
        kind: str,
        onboarding_managed: bool = False,
    ):
        self.kind = kind
        # When configarr also completes onboarding (lingarr.onboarding runs first),
        # a pre-onboarding 403 just means "nothing set yet" rather than an error.
        self.onboarding_managed = onboarding_managed
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self.known_keys = _KNOWN_KEYS[kind]
        self._session = lingarr_session(api_key)

    def _managed(self) -> list[str]:
        return [key for key in self.config if key in self.known_keys]

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        keys = self._managed()
        if not keys:
            return [{}]
        resp = self._session.post(
            f"{self.base_url}/api/setting/multiple/get", json=keys
        )
        if resp.status_code == 403:
            if self.onboarding_managed:
                return [{}]
            raise RuntimeError(
                "Lingarr settings API returned 403 — onboarding is not complete. "
                "Add `onboarding: {enable_user_auth: false}` to this instance so "
                "configarr completes it, or finish the first-run wizard in the UI."
            )
        resp.raise_for_status()
        return [resp.json() or {}]

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        unmanaged = [key for key in self.config if key not in self.known_keys]
        if unmanaged:
            log.warning(
                "Lingarr %s: ignoring setting(s) not known to this group: %s",
                self.kind.split(".", 1)[1],
                ", ".join(sorted(unmanaged)),
            )
        # A null value would encode to the string "None"; skip it rather than write
        # garbage — an unset key keeps its Lingarr value (over-current).
        return [
            {
                key: _encode(self.config[key])
                for key in self._managed()
                if self.config[key] is not None
            }
        ]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # _canonicalize canonicalizes both sides ('true' == True, '300' == 300, and a
        # JSON-array/object string to its object); the engine only compares the desired
        # keys, so extra current keys are harmless. redact_secret_fields fingerprints
        # secret-named values (the *_api_key keys) so a changed key still diffs while
        # its cleartext stays out of the plan.
        canonical = {key: _canonicalize(value) for key, value in resource.items()}
        return redact_secret_fields(canonical)

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp = self._session.post(
            f"{self.base_url}/api/setting/multiple/set", json=dict(action.payload)
        )
        resp.raise_for_status()
        self.invalidate_current()
