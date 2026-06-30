"""Delay-profile provider (Radarr/Sonarr share the API). Client-free: talks HTTP
via requests.

The legacy sync matched delay profiles by the value tuple
``(usenet_delay, torrent_delay, preferred_protocol)``, so changing any of those
values created a *new* profile instead of updating the existing one (rollout
work-list #5 / feasibility §3.3). This provider moves identity to the **tag-set**:
a delay profile in *arr is uniquely addressed by which tags it applies to, and the
built-in catch-all has empty tags. Matching on tags makes the common
single-profile config update the existing profile (id carried through the
over-current merge) rather than duplicating it.

Full-replace resource: a PUT replaces the whole object, so build_desired merges the
config-set overrides over the matched current; unset fields keep their server
value. A config entry whose tag-set is absent from current is created with the
documented defaults.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action, CurrentStateCache

# config key -> API field (straight passthrough of the user's value).
_FIELD_MAP = {
    "enable_usenet": "enableUsenet",
    "enable_torrent": "enableTorrent",
    "preferred_protocol": "preferredProtocol",
    "usenet_delay": "usenetDelay",
    "torrent_delay": "torrentDelay",
    "bypass_if_highest_quality": "bypassIfHighestQuality",
    "minimum_custom_format_score": "minimumCustomFormatScore",
}

# Used only when creating a profile for a tag-set that has no current match; an
# update keeps unset fields at their current server value via merge_full_replace.
_CREATE_DEFAULTS: dict[str, Any] = {
    "enableUsenet": True,
    "enableTorrent": True,
    "preferredProtocol": "torrent",
    "usenetDelay": 0,
    "torrentDelay": 0,
    "bypassIfHighestQuality": True,
    "bypassIfAboveCustomFormatScore": False,
    "minimumCustomFormatScore": 0,
    # The default catch-all order; configarr does not expose ordering.
    "order": 2147483647,
}


class DelayProfileProvider(CurrentStateCache):
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
        return tuple(sorted(resource.get("tags") or []))

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/delayprofile"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    @staticmethod
    def _overrides(entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cfg_key, api_field in _FIELD_MAP.items():
            if cfg_key in entry:
                out[api_field] = entry[cfg_key]
        # An int score in config enables the API's boolean bypass flag.
        if "bypass_if_above_custom_format_score" in entry:
            out["bypassIfAboveCustomFormatScore"] = (
                entry["bypass_if_above_custom_format_score"] > 0
            )
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for entry in self.config:
            overrides = self._overrides(entry)
            overrides["tags"] = sorted(entry.get("tags") or [])
            current = current_by_key.get(tuple(overrides["tags"]))
            if current is None:
                desired.append({**_CREATE_DEFAULTS, **overrides})
            else:
                desired.append(merge_full_replace({}, current, overrides))
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allowlist the managed fields only; unmanaged server fields (e.g. order)
        # are carried through the over-current merge, so they never produce a diff.
        out = {api: coerce_scalar(resource.get(api)) for api in _FIELD_MAP.values()}
        out["bypassIfAboveCustomFormatScore"] = bool(
            resource.get("bypassIfAboveCustomFormatScore", False)
        )
        out["tags"] = sorted(resource.get("tags") or [])
        return out

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
                self._url("/api/v3/delayprofile"), json=action.payload
            )
        elif action.op is Op.UPDATE:
            dp_id = action.payload["id"]
            resp = self._session.put(
                self._url(f"/api/v3/delayprofile/{dp_id}"), json=action.payload
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
