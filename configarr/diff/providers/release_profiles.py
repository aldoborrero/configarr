"""Release-profile provider (Sonarr-only). Client-free: talks HTTP via requests.

Radarr ignores this section entirely; the legacy ``sync_release_profile`` was
write-once (create if the name was absent, otherwise UNCHANGED), so editing a
profile's terms never reached the server (rollout work-list #6). This provider
matches by ``name`` and adds the missing UPDATE path: a config entry whose name
already exists is merged over the current profile and PUT back (id carried
through), while a new name is created with the documented defaults.

Full-replace resource: a PUT replaces the whole object, so build_desired merges
the config-set overrides over the matched current; unset fields keep their server
value.
"""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action, CurrentStateCache

# config key -> API field (straight passthrough of the user's value).
_FIELD_MAP = {
    "enabled": "enabled",
    "required": "required",
    "ignored": "ignored",
    "indexer_id": "indexerId",
    "tags": "tags",
}

# Used only when creating a profile whose name has no current match; an update
# keeps unset fields at their current server value via merge_full_replace.
_CREATE_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "required": [],
    "ignored": [],
    "indexerId": 0,
    "tags": [],
}


class ReleaseProfileProvider(CurrentStateCache):
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or []
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/releaseprofile"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    @staticmethod
    def _overrides(entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cfg_key, api_field in _FIELD_MAP.items():
            if cfg_key in entry:
                out[api_field] = entry[cfg_key]
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for entry in self.config:
            name = entry["name"]
            overrides = {"name": name, **self._overrides(entry)}
            current = current_by_key.get(name)
            if current is None:
                desired.append({**_CREATE_DEFAULTS, **overrides})
            else:
                desired.append(merge_full_replace({}, current, overrides))
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allowlist the managed fields only; unmanaged server fields are carried
        # through the over-current merge, so they never produce a diff. Term lists
        # are unordered, so sort them for a stable comparison.
        return {
            "enabled": bool(resource.get("enabled", True)),
            "required": sorted(resource.get("required") or []),
            "ignored": sorted(resource.get("ignored") or []),
            "indexerId": coerce_scalar(resource.get("indexerId", 0)),
            "tags": sorted(resource.get("tags") or []),
        }

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        if plan.op is Op.CREATE:
            payload = {k: v for k, v in (desired or {}).items() if k != "id"}
            return Action(op=plan.op, key=plan.key, payload=payload)
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is Op.CREATE:
            resp = self._session.post(
                self._url("/api/v3/releaseprofile"), json=action.payload
            )
        elif action.op is Op.UPDATE:
            rp_id = action.payload["id"]
            resp = self._session.put(
                self._url(f"/api/v3/releaseprofile/{rp_id}"), json=action.payload
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
