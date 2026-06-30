"""Radarr custom-format provider. Client-free: talks HTTP via requests."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar, drop_secret_fields
from configarr.diff.providers.base import Action, HttpProvider


class RadarrCustomFormatProvider(HttpProvider):
    kind = "radarr.custom_format"
    prunable = True

    def __init__(self, base_url: str, api_key: str, config: dict[str, Any]):
        super().__init__(base_url, api_key)
        self.config = config or {}
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            self._schema_cache = {
                s["implementation"]: s
                for s in self._get("/api/v3/customformat/schema").json()
            }
        return self._schema_cache

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        name: str = resource["name"]
        return name

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/customformat").json()
        return data

    def _build_spec(self, spec_cfg: dict[str, Any]) -> dict[str, Any]:
        impl = spec_cfg["implementation"]
        template = self._schema().get(impl, {})
        defaults = {f["name"]: f.get("value") for f in template.get("fields", [])}
        merged = {**defaults, **(spec_cfg.get("fields") or {})}
        return {
            "name": spec_cfg["name"],
            "implementation": impl,
            "negate": spec_cfg.get("negate", False),
            "required": spec_cfg.get("required", False),
            "fields": [{"name": k, "value": v} for k, v in merged.items()],
        }

    def build_desired(self) -> list[dict[str, Any]]:
        desired: list[dict[str, Any]] = []
        for name, definition in self.config.items():
            specs = [self._build_spec(s) for s in definition.get("specifications", [])]
            desired.append(
                {
                    "name": name,
                    "includeCustomFormatWhenRenaming": definition.get(
                        "include_when_renaming", False
                    ),
                    "specifications": specs,
                }
            )
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        specs = []
        for spec in resource.get("specifications", []):
            fields = {
                f["name"]: coerce_scalar(f.get("value")) for f in spec.get("fields", [])
            }
            fields = drop_secret_fields(fields)
            specs.append(
                {
                    "name": spec.get("name"),
                    "implementation": spec.get("implementation"),
                    "negate": bool(spec.get("negate", False)),
                    "required": bool(spec.get("required", False)),
                    "fields": fields,
                }
            )
        specs.sort(key=lambda s: (s["name"] or "", s["implementation"] or ""))
        return {
            "includeCustomFormatWhenRenaming": bool(
                resource.get("includeCustomFormatWhenRenaming", False)
            ),
            "specifications": specs,
        }

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE, Op.DELETE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        if plan.op is Op.CREATE:
            return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))
        if plan.op is Op.DELETE:
            # Prune only carries the current object; we just need its id to delete.
            assert current is not None, (
                f"to_action: DELETE for {plan.key!r} requires the current "
                "resource to read its id, got None"
            )
            return Action(op=plan.op, key=plan.key, payload={"id": current["id"]})
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is Op.CREATE:
            self._post("/api/v3/customformat", json=action.payload)
        elif action.op is Op.UPDATE:
            cf_id = action.payload["id"]
            self._put(f"/api/v3/customformat/{cf_id}", json=action.payload)
        elif action.op is Op.DELETE:
            cf_id = action.payload["id"]
            self._delete(f"/api/v3/customformat/{cf_id}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
