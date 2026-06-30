"""Application provider for Prowlarr. Client-free: talks HTTP via requests.

Provider-Field resource (rollout work-list #10): the object carries a ``fields``
list whose shape comes from ``/applications/schema``. Prowlarr uses the
``/api/v1`` base path. Full-replace + over current: a matched application keeps
its server field values, with only the configured ``settings`` overlaid, so an
apply never resets fields the user did not set. A new application is built from
the schema defaults.

Applications carry a ``syncLevel`` (the Prowlarr ``ApplicationSyncLevel`` enum)
rather than the indexer-only ``priority``/``appProfileId``/``redirect`` keys.
The schema is resolved by ``implementation`` only (no Cardigann ``definition``).
Secret fields (apiKey/password) are echoed masked, so they are skipped from the
diff by name (apply still sends the real value). PUT/POST pass ``forceSave=true``
to skip the live connectivity test.
"""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import (
    coerce_scalar,
    drop_secret_fields,
    secret_field_names,
)
from configarr.diff.providers.base import Action, CurrentStateCache

# Valid ApplicationSyncLevel values (mirrors the generated client enum, kept local
# so configarr/diff stays free of generated-client imports).
SYNC_LEVELS = frozenset({"disabled", "addOnly", "fullSync"})


class ApplicationProvider(CurrentStateCache):
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key
        self._schema_cache: dict[str, dict[str, Any]] | None = None
        self._secret_names: set[str] = set()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _schemas(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            resp = self._session.get(self._url("/api/v1/applications/schema"))
            resp.raise_for_status()
            by_impl: dict[str, dict[str, Any]] = {}
            for s in resp.json():
                impl = s.get("implementation")
                if impl and impl not in by_impl:
                    by_impl[impl] = s
            self._schema_cache = by_impl
        return self._schema_cache

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v1/applications"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    def _overlay_fields(
        self, base_fields: list[dict[str, Any]], settings: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Overlay configured settings onto a field list, keeping each field's
        existing value (current on update, schema default on create) when unset."""
        self._secret_names |= secret_field_names(base_fields)
        out: list[dict[str, Any]] = []
        for f in base_fields:
            name = f["name"]
            value = settings.get(name, f.get("value"))
            out.append({"name": name, "value": value})
        return out

    @staticmethod
    def _sync_level(definition: dict[str, Any]) -> str:
        level: str = definition.get("sync_level", "fullSync")
        if level not in SYNC_LEVELS:
            raise ValueError(f"Invalid sync_level: {level!r}")
        return level

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, definition in self.config.items():
            settings = definition.get("settings") or {}
            overrides = {
                "name": name,
                "syncLevel": self._sync_level(definition),
                "tags": definition.get("tags", []),
            }
            current = current_by_key.get(name)
            if current is None:
                impl = definition.get("implementation")
                if not impl:
                    raise ValueError(
                        f"Missing 'implementation' for application: {name}"
                    )
                schema = self._schemas().get(impl, {})
                desired.append(
                    {
                        **overrides,
                        "implementation": impl,
                        "configContract": schema.get("configContract"),
                        "fields": self._overlay_fields(
                            schema.get("fields") or [], settings
                        ),
                    }
                )
            else:
                overrides["fields"] = self._overlay_fields(
                    current.get("fields") or [], settings
                )
                desired.append(merge_full_replace({}, current, overrides))
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        fields = {
            f["name"]: coerce_scalar(f.get("value")) for f in resource.get("fields", [])
        }
        fields = drop_secret_fields(fields, self._secret_names)
        return {
            "syncLevel": resource.get("syncLevel", "fullSync"),
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "tags": sorted(resource.get("tags") or []),
            "fields": fields,
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
                self._url("/api/v1/applications?forceSave=true"), json=action.payload
            )
        elif action.op is Op.UPDATE:
            app_id = action.payload["id"]
            resp = self._session.put(
                self._url(f"/api/v1/applications/{app_id}?forceSave=true"),
                json=action.payload,
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
