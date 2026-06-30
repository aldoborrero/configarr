"""Bazarr settings-section provider (rollout work-list #15). Client-free: talks
HTTP via requests.

Bazarr's ``general``/``sonarr``/``radarr`` settings each live as one section of the
single ``GET /api/system/settings`` document. This provider owns one section
(its ``kind`` is ``bazarr.<section>``) and treats it as a singleton: ``fetch_current``
GETs the whole document, extracts the section, and wraps it so the engine can index
it; ``match_key`` returns a fixed sentinel so the only op is UPDATE.

The settings API is set-only and partial — writes go through a form-POST of
``settings-<section>-<field>=value`` fields (bools lower-cased), each POST touching
only the fields it carries. So this is an over-current provider: build_desired only
emits the keys the user set, and the diff compares those keys against the current
section. Every unmanaged server key stays out of the plan because the engine only
diffs the desired keys.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import requests

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action, CurrentStateCache


def _form_value(value: Any) -> str:
    """Encode a value the way Bazarr's settings form-POST expects: bools as the
    lower-cased ``true``/``false`` string, everything else stringified."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


class BazarrSettingsProvider(CurrentStateCache):
    """Diffs a single Bazarr settings section (singleton keyed by section name)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        # kind is "bazarr.<section>"; the section is the trailing segment.
        self.section = kind.split(".", 1)[1]
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self._session = requests.Session()

    def _settings_url(self) -> str:
        return f"{self.base_url}/api/system/settings"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        # Singleton per section: identity is the section itself.
        return self.section

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._settings_url(), params={"apikey": self.api_key})
        resp.raise_for_status()
        settings = resp.json() or {}
        # Wrap the one section object so the engine can index it like any list.
        return [settings.get(self.section, {})]

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        # Only the keys the user set; the form-POST is partial so unset keys keep
        # their server value. Raw values; bool/scalar canonicalization happens in
        # normalize (diff) and _form_value (apply).
        return [dict(self.config)]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # coerce_scalar canonicalizes both sides so '25' == 25 and 'true' == True;
        # the engine only compares the desired keys, so carrying extra current keys
        # here is harmless.
        return {key: coerce_scalar(value) for key, value in resource.items()}

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
        files = {
            f"settings-{self.section}-{field}": (None, _form_value(value))
            for field, value in action.payload.items()
        }
        resp = self._session.post(
            self._settings_url(), params={"apikey": self.api_key}, files=files
        )
        resp.raise_for_status()
        self.invalidate_current()
