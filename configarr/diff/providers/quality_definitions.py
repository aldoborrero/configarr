"""Quality-definition provider (Radarr/Sonarr share the API). Client-free: talks
HTTP via requests.

Quality definitions are the server's built-in qualities; they are never created,
only their size limits are updated. The config lists only the qualities to touch
(``profiles.quality_definitions`` keyed by quality name), each setting any of
``min``/``max``/``preferred``. build_desired emits one full object per *listed*
quality that exists on the instance, merging the requested sizes over current so
the PUT carries title/weight/quality untouched. Diffing per-quality (instead of
the legacy bulk PUT) is what fixes the resource always reporting UPDATED.
"""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action

# config key -> API field
_SIZE_FIELDS = {"min": "minSize", "max": "maxSize", "preferred": "preferredSize"}


class QualityDefinitionProvider:
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource.get("quality") or {}).get("name")

    def fetch_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/qualitydefinition"))
        resp.raise_for_status()
        return resp.json()

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_name = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, cfg in self.config.items():
            current = current_by_name.get(name)
            if current is None:
                # Quality not present on the instance: nothing to update.
                continue
            sizes = {
                api_field: cfg[key]
                for key, api_field in _SIZE_FIELDS.items()
                if key in cfg
            }
            desired.append(merge_full_replace({}, current, sizes))
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        quality = resource.get("quality") or {}
        return {
            "quality": quality.get("id"),
            "minSize": coerce_scalar(resource.get("minSize")),
            "maxSize": coerce_scalar(resource.get("maxSize")),
            "preferredSize": coerce_scalar(resource.get("preferredSize")),
        }

    def to_action(
        self, plan: ResourcePlan, current: dict | None, desired: dict | None
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        qd_id = action.payload["id"]
        resp = self._session.put(
            self._url(f"/api/v3/qualitydefinition/{qd_id}"), json=action.payload
        )
        resp.raise_for_status()
