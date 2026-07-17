"""Download-client provider (Radarr and Sonarr share the resource). Client-free:
talks HTTP via requests.

Provider-Field resource (rollout work-list #7): the object carries a ``fields``
list whose shape comes from ``/downloadclient/schema``. Full-replace + over current:
a matched client keeps its server field values, with only the configured ``settings``
overlaid, so an apply never resets fields the user did not set. A new client is built
from the schema defaults. apiKey/password are echoed masked, so they are skipped from
the diff by name (apply still sends the real value). PUT/POST pass ``forceSave=true``
to skip the live connectivity test the *arr API would otherwise run.
"""

from __future__ import annotations

from typing import Any

from configarr.build import merge_full_replace
from configarr.normalize import coerce_scalar
from configarr.providers.base import Action, FieldProvider


class DownloadClientProvider(FieldProvider):
    """Diffs Radarr/Sonarr download clients by name (provider-Field resource)."""

    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key, config, kind)
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            self._schema_cache = {
                s["implementation"]: s
                for s in self._get("/api/v3/downloadclient/schema").json()
            }
        return self._schema_cache

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/downloadclient").json()
        return data

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
                "tags": self._resolve_tags(definition.get("tags")),
            }
            current = current_by_key.get(name)
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
        return {
            "enable": bool(resource.get("enable", True)),
            "priority": coerce_scalar(resource.get("priority", 1)),
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "protocol": resource.get("protocol"),
            "tags": sorted(resource.get("tags") or []),
            "fields": self._normalized_fields(resource),
        }

    def apply(self, action: Action) -> int | None:
        return self._apply_force_save("/api/v3/downloadclient", action)
