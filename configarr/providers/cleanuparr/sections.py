"""Cleanuparr singleton config sections. Client-free: talks HTTP via requests.

Each section is one object read with ``GET /api/configuration/<section>`` and
written with ``PUT`` of the same path: ``general``, ``queue_cleaner``,
``download_cleaner`` and ``malware_blocker``, plus the per-*arr settings object
(``/api/configuration/sonarr``, … — only ``failedImportMaxStrikes`` is writable
there; its ``instances`` are a separate provider).

The PUT is full-replace: Cleanuparr resets every omitted field to its default. So
this is an over-current provider — build_desired merges the configured keys over
the current object (see ``common.merge_over``) and the whole merged object is
written back. The diff is over dotted paths (``failedImport.maxStrikes``), so a plan
names exactly the settings that change.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any

from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.cleanuparr.common import (
    cleanuparr_session,
    flatten,
    merge_over,
)

log = logging.getLogger(__name__)

# Read-only or separately managed keys a section GET returns: identity, the arr
# instance list and the download cleaner's per-client sub-configs. Kept out of both
# the diff and the PUT body.
READ_ONLY_KEYS = frozenset({"id", "type", "instances", "clients"})

# The *arr types Cleanuparr has a config object for (path segment under
# /api/configuration/).
ARR_TYPES: tuple[str, ...] = (
    "sonarr",
    "radarr",
    "lidarr",
    "readarr",
    "whisparr",
    "sportarr",
    "lazylibrarian",
)
_SINGLETON = "settings"


def _strip(obj: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in obj.items() if k not in READ_ONLY_KEYS}


class CleanuparrSectionProvider(CurrentStateCache):
    """Diffs one Cleanuparr config object (singleton, UPDATE-only)."""

    def __init__(
        self, base_url: str, api_key: str, config: Any, kind: str, path: str
    ) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.config = config or {}
        self._session = cleanuparr_session(api_key)

    def _url(self) -> str:
        return f"{self.base_url}/api/configuration/{self.path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        resp = self._session.get(self._url())
        resp.raise_for_status()
        return [_strip(resp.json() or {})]

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current = self.fetch_current()
        base = current[0] if current else {}
        return [_strip(merge_over(base, self.config))]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return flatten(resource)

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
        resp = self._session.put(self._url(), json=dict(action.payload))
        resp.raise_for_status()
        self.invalidate_current()


class CleanuparrArrSettingsProvider(CurrentStateCache):
    """The per-*arr settings objects (``failed_import_max_strikes``), keyed by arr
    type. One provider covers every arr type configured under ``arr:``."""

    def __init__(self, base_url: str, api_key: str, arr: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        # arr type -> its settings, minus the instance map (another provider).
        self.config: dict[str, dict[str, Any]] = {}
        for arr_type, body in (arr or {}).items():
            settings = {k: v for k, v in (body or {}).items() if k != "instances"}
            if arr_type not in ARR_TYPES:
                raise ValueError(
                    f"Cleanuparr: unknown arr type '{arr_type}' "
                    f"(expected one of {', '.join(ARR_TYPES)})"
                )
            if settings:
                self.config[arr_type] = settings
        self._session = cleanuparr_session(api_key)

    def _url(self, arr_type: str) -> str:
        return f"{self.base_url}/api/configuration/{arr_type}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return str(resource["_arr"])

    def _load_current(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for arr_type in self.config:
            resp = self._session.get(self._url(arr_type))
            resp.raise_for_status()
            out.append({"_arr": arr_type, **_strip(resp.json() or {})})
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current = {c["_arr"]: c for c in self.fetch_current()}
        return [
            {"_arr": arr_type, **_strip(merge_over(current.get(arr_type, {}), cfg))}
            for arr_type, cfg in self.config.items()
        ]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return flatten({k: v for k, v in resource.items() if k != "_arr"})

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
        body = {k: v for k, v in action.payload.items() if k != "_arr"}
        resp = self._session.put(self._url(str(action.key)), json=body)
        resp.raise_for_status()
        self.invalidate_current()
