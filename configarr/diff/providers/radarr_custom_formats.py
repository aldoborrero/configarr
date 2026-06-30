"""Radarr custom-format provider. Client-free: talks HTTP via requests."""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar, drop_masked_secrets
from configarr.diff.providers.base import Action, CurrentStateCache


class RadarrCustomFormatProvider(CurrentStateCache):
    kind = "radarr.custom_format"
    prunable = True

    def __init__(self, base_url: str, api_key: str, config: dict[str, Any]):
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            resp = self._session.get(self._url("/api/v3/customformat/schema"))
            resp.raise_for_status()
            self._schema_cache = {s["implementation"]: s for s in resp.json()}
        return self._schema_cache

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        name: str = resource["name"]
        return name

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/customformat"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
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
            fields = drop_masked_secrets(fields)
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
            return Action(
                op=plan.op, key=plan.key, payload={"id": (current or {})["id"]}
            )
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is Op.CREATE:
            resp = self._session.post(
                self._url("/api/v3/customformat"), json=action.payload
            )
        elif action.op is Op.UPDATE:
            cf_id = action.payload["id"]
            resp = self._session.put(
                self._url(f"/api/v3/customformat/{cf_id}"), json=action.payload
            )
        elif action.op is Op.DELETE:
            cf_id = action.payload["id"]
            resp = self._session.delete(self._url(f"/api/v3/customformat/{cf_id}"))
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
