"""Kapowarr settings: one singleton object (``GET``/``PUT /api/settings``).

Verified against Kapowarr V1.3.2 (``frontend/api.py``, ``backend/internals/
settings.py``): the ``PUT`` is a **partial** update (``Settings.update`` works like
``dict.update``), so only the keys that change are sent and every other setting is
left alone. Config keys are Kapowarr's own snake_case setting names.

Comparison follows how Kapowarr stores each value, so an unchanged config does not
diff: folders (``download_folder``, ``db_backup_folder``) are kept with a trailing
``/``; ``flaresolverr_base_url`` loses its trailing slash and gains ``http://``;
``url_base`` is ``/``-prefixed without a trailing slash; ``comicvine_api_key`` is
stripped. ``comicvine_api_key`` comes back in clear text and is compared by
fingerprint; ``auth_username``, ``auth_password`` and ``proxy_password`` come back
masked, so they are never diffed (they are sent along whenever another setting
changes). ``api_key`` cannot be set through the API.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any

from configarr.normalize import coerce_scalar, redact_secret_fields
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action
from configarr.providers.kapowarr.common import KapowarrProvider, norm_base_url

log = logging.getLogger(__name__)

# Echoed masked: compared never, sent with any other change.
MASKED = frozenset({"auth_username", "auth_password", "proxy_password"})
FOLDERS = frozenset({"download_folder", "db_backup_folder"})
_SINGLETON = "settings"


def _compare_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        if key in FOLDERS and value:
            return value if value.endswith("/") else f"{value}/"
        if key == "flaresolverr_base_url":
            return norm_base_url(value)
        if key == "url_base" and value:
            return ("/" + value.lstrip("/")).rstrip("/")
        if key == "comicvine_api_key":
            return value.strip()
    return coerce_scalar(value)


class KapowarrSettingsProvider(KapowarrProvider):
    """Diffs Kapowarr's settings object (singleton, UPDATE-only)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: dict[str, Any] = dict(config or {})
        if "api_key" in self.config:
            raise ValueError(
                "Kapowarr settings: 'api_key' cannot be set through the API "
                "(Kapowarr only regenerates it); remove it from settings"
            )

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return [dict(self._get("/settings") or {})]

    def _known(self) -> dict[str, Any]:
        """The configured settings Kapowarr knows; unknown keys are warned about."""
        current = self.fetch_current()
        server = current[0] if current else {}
        unknown = sorted(k for k in self.config if k not in server)
        if unknown:
            log.warning(
                "Kapowarr settings: ignoring unknown setting(s): %s", ", ".join(unknown)
            )
        return {k: v for k, v in self.config.items() if k in server}

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current = self.fetch_current()
        return [{**(current[0] if current else {}), **self._known()}]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return redact_secret_fields(
            {
                k: _compare_value(k, v)
                for k, v in resource.items()
                if k not in MASKED and k != "api_key"
            }
        )

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        current = current or {}
        payload = {
            k: v
            for k, v in self._known().items()
            if k in MASKED or _compare_value(k, v) != _compare_value(k, current.get(k))
        }
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self._call("PUT", "/settings", json=dict(action.payload))
        self.invalidate_current()
