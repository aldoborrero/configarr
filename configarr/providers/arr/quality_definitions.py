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

import logging
from collections.abc import Hashable
from typing import Any

from configarr.build import merge_full_replace
from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, HttpProvider

log = logging.getLogger(__name__)

# config key -> API field
_SIZE_FIELDS = {"min": "minSize", "max": "maxSize", "preferred": "preferredSize"}


class QualityDefinitionProvider(HttpProvider):
    """Diffs Radarr/Sonarr quality definitions by quality name (update-only)."""

    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config = config or {}

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource.get("quality") or {}).get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/qualitydefinition").json()
        return data

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_name = {self.match_key(c): c for c in self.fetch_current()}
        # Quality names are matched case-insensitively (as quality_profiles does), so a
        # config key whose case differs from the server's still finds its definition.
        by_lower = {
            k.lower(): v for k, v in current_by_name.items() if isinstance(k, str)
        }
        desired: list[dict[str, Any]] = []
        for name, cfg in self.config.items():
            current = current_by_name.get(name) or by_lower.get(str(name).lower())
            if current is None:
                log.warning(
                    "quality definition %r not found on %s; ignored",
                    name,
                    self.kind.split(".")[0],
                )
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
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        qd_id = action.payload["id"]
        self._put(f"/api/v3/qualitydefinition/{qd_id}", json=action.payload)
        self.invalidate_current()
