"""Notification (connection) provider for Radarr and Sonarr. Client-free: talks
HTTP via requests.

Provider-Field resource (rollout work-list #8): the object carries a ``fields``
list whose shape comes from ``/notification/schema``. Full-replace + over current:
a matched notification keeps its server field values, with only the configured
``settings`` overlaid, so an apply never resets fields the user did not set. A new
notification is built from the schema defaults. Secret fields (apiKey/token/...)
are echoed masked, so they are skipped from the diff by name (apply still sends the
real value). ``onImportComplete`` is Sonarr-only — Radarr never reads it. PUT/POST
pass ``forceSave=true`` to skip the live connectivity test the *arr API would run.
"""

from __future__ import annotations

from typing import Any

from configarr.build import merge_full_replace
from configarr.providers.base import Action, FieldProvider


class NotificationProvider(FieldProvider):
    """Diffs Radarr/Sonarr notification connections by name (provider-Field)."""

    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key, config, kind)
        self.is_sonarr = kind.startswith("sonarr")
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            self._schema_cache = {
                s["implementation"]: s
                for s in self._get("/api/v3/notification/schema").json()
            }
        return self._schema_cache

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/notification").json()
        return data

    def _event_flags(self, definition: dict[str, Any]) -> dict[str, Any]:
        flags = {
            "onDownload": definition.get("on_download", True),
            "onUpgrade": definition.get("on_upgrade", True),
            "onRename": definition.get("on_rename", True),
        }
        if self.is_sonarr:
            flags["onImportComplete"] = definition.get("on_import_complete", True)
        return flags

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
                "tags": self._resolve_tags(definition.get("tags")),
                **self._event_flags(definition),
            }
            current = current_by_key.get(name)
            if current is None:
                impl = definition.get("implementation")
                if not impl:
                    raise ValueError(
                        f"Missing 'implementation' for notification: {name}"
                    )
                schema = self._schema().get(impl, {})
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
        out = {
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "onDownload": bool(resource.get("onDownload", True)),
            "onUpgrade": bool(resource.get("onUpgrade", True)),
            "onRename": bool(resource.get("onRename", True)),
            "tags": sorted(resource.get("tags") or []),
            "fields": self._normalized_fields(resource),
        }
        if self.is_sonarr:
            out["onImportComplete"] = bool(resource.get("onImportComplete", True))
        return out

    def apply(self, action: Action) -> None:
        self._apply_force_save("/api/v3/notification", action)
