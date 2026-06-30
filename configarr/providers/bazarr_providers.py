"""Bazarr subtitle-provider provider (rollout work-list #16). Client-free: talks
HTTP via requests.

Each subtitle provider configarr manages lives as one top-level section of the
single ``GET /api/system/settings`` document, keyed by the provider's Bazarr name,
while the enabled set lives in ``general.enabled_providers``. This provider plans one
resource per configured provider: identity is the Bazarr name, so the config name is
mapped through a small rename table (only ``submate`` → ``whisperai``; every other
name passes through verbatim).

The settings API is set-only and partial — writes go through a form-POST of
``settings-<provider>-<field>=value`` fields (bools lower-cased), each POST touching
only the fields it carries. So this is an over-current provider: build_desired emits
only the keys the user set plus a synthetic ``enabled`` marker, and the engine
compares those keys against the current section. ``enabled_providers`` is
force-managed additively: apply re-reads the current list and adds this provider,
never removing others.

Secret handling differs from the *arr providers: Bazarr's ``GET /api/system/settings``
returns secrets in CLEARTEXT and uses no mask sentinel (verified against Bazarr's
``app/config.get_settings``, which only strips ``flask_secret_key``). Idempotency for
password/apikey fields therefore works by direct value comparison, so the
``drop_secret_fields`` call in ``normalize`` is purely defensive against a literal
``"********"`` value and is a no-op against real Bazarr output.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import requests

from configarr.model import Op, ResourcePlan
from configarr.normalize import coerce_scalar, drop_secret_fields
from configarr.providers.base import Action, CurrentStateCache

# The only config-name → Bazarr-name rename; all other names are used verbatim.
PROVIDER_NAME_MAP = {"submate": "whisperai"}

# Synthetic key folded into the diffed resource: a configured provider must be
# enabled, so a not-yet-enabled provider surfaces an enabled False→True change. It
# is not a real provider field — apply translates it into the enabled_providers write
# rather than a settings-<provider>-enabled form field.
ENABLED_KEY = "enabled"


def _form_value(value: Any) -> str:
    """Encode a value the way Bazarr's settings form-POST expects: bools as the
    lower-cased ``true``/``false`` string, everything else stringified."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


class BazarrProviderProvider(CurrentStateCache):
    """Diffs Bazarr subtitle providers by name."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self._session = requests.Session()

    def _settings_url(self) -> str:
        return f"{self.base_url}/api/system/settings"

    def _get_settings(self) -> dict[str, Any]:
        resp = self._session.get(self._settings_url(), params={"apikey": self.api_key})
        resp.raise_for_status()
        return resp.json() or {}

    @staticmethod
    def _bazarr_name(config_name: str) -> str:
        return PROVIDER_NAME_MAP.get(config_name, config_name)

    @staticmethod
    def _enabled_list(settings: dict[str, Any]) -> list[str]:
        """Read general.enabled_providers as a clean list of names, dropping the
        malformed JSON-string entries Bazarr sometimes returns (mirrors the legacy
        sync_provider normalization)."""
        raw = (settings.get("general") or {}).get("enabled_providers", [])
        if not isinstance(raw, list):
            return []
        return [
            item for item in raw if isinstance(item, str) and not item.startswith("[")
        ]

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        settings = self._get_settings()
        enabled = self._enabled_list(settings)
        current: list[dict[str, Any]] = []
        for config_name in self.config:
            bazarr_name = self._bazarr_name(config_name)
            section = settings.get(bazarr_name) or {}
            resource = {"name": bazarr_name, ENABLED_KEY: bazarr_name in enabled}
            resource.update(section)
            current.append(resource)
        return current

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        desired: list[dict[str, Any]] = []
        for config_name, settings in self.config.items():
            bazarr_name = self._bazarr_name(config_name)
            resource: dict[str, Any] = {"name": bazarr_name, ENABLED_KEY: True}
            for field, value in (settings or {}).items():
                resource[field] = value
            desired.append(resource)
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        cleaned = drop_secret_fields(resource)
        return {key: coerce_scalar(value) for key, value in cleaned.items()}

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
        bazarr_name = str(action.key)
        files: dict[str, tuple[None, str]] = {}
        for field, value in action.payload.items():
            if field in ("name", ENABLED_KEY):
                continue
            files[f"settings-{bazarr_name}-{field}"] = (None, _form_value(value))
        # enabled_providers is additively managed: re-read the live list and add this
        # provider, leaving every other enabled provider in place.
        enabled = self._enabled_list(self._get_settings())
        if bazarr_name not in enabled:
            enabled.append(bazarr_name)
        files["settings-general-enabled_providers"] = (None, ",".join(enabled))
        resp = self._session.post(
            self._settings_url(), params={"apikey": self.api_key}, files=files
        )
        resp.raise_for_status()
        self.invalidate_current()
