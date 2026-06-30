"""Download-client provider for Prowlarr. Client-free: talks HTTP via requests.

Provider-Field resource (rollout work-list #11): the object carries a ``fields``
list whose shape comes from ``/downloadclient/schema``. Prowlarr uses the
``/api/v1`` base path. Full-replace + over current: a matched client keeps its
server field values, with only the configured ``settings`` overlaid, so an apply
never resets fields the user did not set. A new client is built from the schema
defaults.

Prowlarr deltas from the Radarr/Sonarr download-client provider (#7):
- name is matched **case-insensitively** (Prowlarr stores clients added by other
  tools with inconsistent casing);
- a field value is substituted None -> schema default -> ``""`` so Prowlarr never
  receives a null field (which raises a NullReferenceException server-side);
- ``categories`` is hardcoded to ``[]`` (configarr does not manage per-client
  categories on Prowlarr).

apiKey/password are echoed masked, so they are skipped from the diff by name
(apply still sends the real value). PUT/POST pass ``forceSave=true`` to skip the
live connectivity test.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import (
    coerce_scalar,
    drop_secret_fields,
    secret_field_names,
)
from configarr.diff.providers.base import Action, HttpProvider


class ProwlarrDownloadClientProvider(HttpProvider):
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config = config or {}
        self._schema_cache: dict[str, dict[str, Any]] | None = None
        # ``_secret_names_ready`` makes normalize() self-enforcing: it triggers a
        # build first if called before build_desired() has populated the set.
        self._secret_names: set[str] = set()
        self._secret_names_ready = False

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            self._schema_cache = {
                s["implementation"]: s
                for s in self._get("/api/v1/downloadclient/schema").json()
            }
        return self._schema_cache

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        name = resource.get("name")
        return name.lower() if isinstance(name, str) else name

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v1/downloadclient").json()
        return data

    def _overlay_fields(
        self, base_fields: list[dict[str, Any]], settings: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Overlay configured settings onto a field list, keeping each field's
        existing value (current on update, schema default on create) when unset.
        A None value is substituted with ``""`` so Prowlarr never gets a null."""
        self._secret_names |= secret_field_names(base_fields)
        out: list[dict[str, Any]] = []
        for f in base_fields:
            name = f["name"]
            value = settings.get(name)
            if value is None:
                value = f.get("value")
            if value is None:
                value = ""
            out.append({"name": name, "value": value})
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        self._secret_names_ready = True
        if not self.config:
            return []
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, definition in self.config.items():
            settings = definition.get("settings") or {}
            overrides = {
                "name": name,
                "enable": definition.get("enable", True),
                "priority": definition.get("priority", 1),
                "categories": [],
                "tags": definition.get("tags", []),
            }
            current = current_by_key.get(self.match_key({"name": name}))
            if current is None:
                impl = definition.get("implementation")
                if not impl:
                    raise ValueError(
                        f"Missing 'implementation' for download client: {name}"
                    )
                schema = self._schema().get(impl, {})
                desired.append(
                    {
                        **overrides,
                        "implementation": impl,
                        "configContract": schema.get("configContract"),
                        "protocol": schema.get("protocol"),
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
        if not self._secret_names_ready:
            self.build_desired()
        fields = {
            f["name"]: coerce_scalar(f.get("value")) for f in resource.get("fields", [])
        }
        fields = drop_secret_fields(fields, self._secret_names)
        return {
            "enable": bool(resource.get("enable", True)),
            "priority": coerce_scalar(resource.get("priority", 1)),
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "protocol": resource.get("protocol"),
            "categories": sorted(resource.get("categories") or []),
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
            self._post("/api/v1/downloadclient?forceSave=true", json=action.payload)
        elif action.op is Op.UPDATE:
            dc_id = action.payload["id"]
            self._put(
                f"/api/v1/downloadclient/{dc_id}?forceSave=true", json=action.payload
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
