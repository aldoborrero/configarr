"""SABnzbd misc-settings provider (rollout work-list #14). Client-free: talks
HTTP via requests.

Misc is SABnzbd's global-settings singleton: a flat object of many keys, of which
only an allow-list is managed here. Like the server/category providers it uses the
set-only config API, but writes are per-keyword
(``GET /api?mode=set_config&section=misc&keyword=<key>&value=<value>``), one call
per managed key, leaving every other key at its server value. So this is an
over-current (not full-replace) provider: a managed key the user did not set keeps
its current server value; the plan is computed client-side by GETting
``mode=get_config&section=misc`` and diffing only the allow-listed keys.

Identity is the singleton itself (there is no per-object id and no name), so
``match_key`` returns a fixed sentinel and the only op is UPDATE. Bools are encoded
as ``1``/``0`` to match SABnzbd's wire shape. Unmanaged server keys (e.g. the echoed
``api_key``) stay out of the diff via the allow-list normalize.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import requests

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action, CurrentStateCache

# The allow-listed misc keys this provider manages (mirrors the legacy
# sync_misc_settings key_map, which maps config keys 1:1 to SABnzbd API keys).
MISC_KEYS: tuple[str, ...] = (
    "download_dir",
    "complete_dir",
    "nzb_backup_dir",
    "scripts_dir",
    "log_dir",
    "bandwidth_max",
    "bandwidth_perc",
    "cache_limit",
    "pause_on_post_processing",
    "auto_sort",
    "enable_all_par",
    "enable_recursive",
    "par_option",
    "nice",
    "ionice",
    "pre_check",
    "auto_disconnect",
    "flat_unpack",
    "safe_postproc",
)

# Singleton identity: misc has no id and no name, so it is addressed by a fixed key.
_MISC_KEY = "misc"


def _encode(value: Any) -> Any:
    """Encode a bool as SABnzbd's 1/0 wire shape; pass other scalars through."""
    if isinstance(value, bool):
        return 1 if value else 0
    return value


class SabnzbdMiscProvider(CurrentStateCache):
    """Diffs the SABnzbd misc-settings singleton."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = config or {}
        self._session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /api with the apikey/output params SABnzbd requires, raising on the
        in-body error SABnzbd returns with a 200 status."""
        query = {**params, "apikey": self.api_key, "output": "json"}
        resp = self._session.get(self._url("/api"), params=query)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"SABnzbd API error: {data['error']}")
        return data

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _MISC_KEY

    def _load_current(self) -> list[dict[str, Any]]:
        data = self._call({"mode": "get_config", "section": "misc"})
        # Singleton: wrap the one object so the engine can index it like any list.
        return [data.get("config", {}).get("misc", {})]

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        [current] = self.fetch_current()
        # Carry the current values for managed keys the user did not set.
        base = {k: current[k] for k in MISC_KEYS if k in current}
        overrides = {
            key: _encode(self.config[key]) for key in MISC_KEYS if key in self.config
        }
        return [{**base, **overrides}]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allowlist the managed keys only; unmanaged server keys (e.g. api_key)
        # never produce a diff.
        out: dict[str, Any] = {}
        for key in MISC_KEYS:
            if key not in resource:
                continue
            out[key] = coerce_scalar(_encode(resource[key]))
        return out

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
        for keyword, value in action.payload.items():
            self._call(
                {
                    "mode": "set_config",
                    "section": "misc",
                    "keyword": keyword,
                    "value": value,
                }
            )
        self.invalidate_current()
