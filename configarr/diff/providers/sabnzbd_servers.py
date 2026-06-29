"""SABnzbd news-server provider (rollout work-list #12). Client-free: talks HTTP
via requests.

SABnzbd's config API is set-only: there is no per-object id and no full-document
PUT. Each server is addressed by ``name`` and written with
``GET /api?mode=set_config&section=servers&name=<name>&<field>=<value>...`` — and
crucially ``set_config`` only writes the keys it is given, leaving every other key
at its server value. So this is an over-current (not full-replace) provider: a
matched server keeps its current field values, with only the configured settings
overlaid; a new server is built from documented defaults. The plan is computed
client-side by GETting ``mode=get_config&section=servers`` and diffing, which is
what makes plan status meaningful for an otherwise blind set-only API.

Bools are encoded as ``1``/``0`` to match SABnzbd's wire shape. The ``password`` is
never echoed in clear text, so it is skipped from the diff by name (apply still
sends the real value from the config).
"""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action

# Documented defaults for a brand-new server (mirrors the legacy sync_server).
# host has no default — it is required and identifies the upstream.
SERVER_DEFAULTS: dict[str, Any] = {
    "port": 563,
    "ssl": 1,
    "ssl_verify": 2,
    "ssl_ciphers": "",
    "username": "",
    "password": "",
    "connections": 8,
    "priority": 0,
    "retention": 0,
    "timeout": 60,
    "enable": 1,
    "required": 0,
    "optional": 0,
    "send_group": 0,
    "notes": "",
}

# Every managed key in identity-then-defaults order.
MANAGED_KEYS: tuple[str, ...] = ("name", "host", *SERVER_DEFAULTS.keys())

# Skipped from the diff (and never carried from the masked server value).
SECRET_KEYS = frozenset({"password"})


def _encode(value: Any) -> Any:
    """Encode a bool as SABnzbd's 1/0 wire shape; pass other scalars through."""
    if isinstance(value, bool):
        return 1 if value else 0
    return value


class SabnzbdServerProvider:
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
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(f"SABnzbd API error: {data['error']}")
        return data

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def fetch_current(self) -> list[dict[str, Any]]:
        data = self._call({"mode": "get_config", "section": "servers"})
        return data.get("config", {}).get("servers", [])

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, settings in self.config.items():
            settings = settings or {}
            host = settings.get("host")
            if not host:
                raise ValueError(f"SABnzbd server '{name}' is missing required 'host'")
            current = current_by_key.get(name)
            if current is None:
                base = dict(SERVER_DEFAULTS)
            else:
                # Carry the current server values for keys the user did not set,
                # except the masked secret which must come from config when set.
                base = {
                    k: current[k]
                    for k in MANAGED_KEYS
                    if k in current and k not in SECRET_KEYS
                }
            overrides: dict[str, Any] = {"name": name, "host": host}
            for key in MANAGED_KEYS:
                if key in settings:
                    overrides[key] = _encode(settings[key])
            desired.append({**base, **overrides})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in MANAGED_KEYS:
            if key in SECRET_KEYS or key not in resource:
                continue
            out[key] = coerce_scalar(_encode(resource[key]))
        return out

    def to_action(
        self, plan: ResourcePlan, current: dict | None, desired: dict | None
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op not in (Op.CREATE, Op.UPDATE):
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        params: dict[str, Any] = {
            "mode": "set_config",
            "section": "servers",
            "name": action.key,
        }
        for key, value in action.payload.items():
            if key == "name":
                continue
            params[key] = value
        self._call(params)
