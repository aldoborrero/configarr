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

from typing import Any

from configarr.diff.build import merge_full_replace
from configarr.diff.providers.base import Action, FieldProvider

# Valid ApplicationSyncLevel values (mirrors the generated client enum, kept local
# so configarr/diff stays free of generated-client imports).
SYNC_LEVELS = frozenset({"disabled", "addOnly", "fullSync"})


class ApplicationProvider(FieldProvider):
    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key, config, kind)
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _schemas(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            by_impl: dict[str, dict[str, Any]] = {}
            for s in self._get("/api/v1/applications/schema").json():
                impl = s.get("implementation")
                if impl and impl not in by_impl:
                    by_impl[impl] = s
            self._schema_cache = by_impl
        return self._schema_cache

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v1/applications").json()
        return data

    @staticmethod
    def _sync_level(definition: dict[str, Any]) -> str:
        level: str = definition.get("sync_level", "fullSync")
        if level not in SYNC_LEVELS:
            raise ValueError(f"Invalid sync_level: {level!r}")
        return level

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
        return {
            "syncLevel": resource.get("syncLevel", "fullSync"),
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "tags": sorted(resource.get("tags") or []),
            "fields": self._normalized_fields(resource),
        }

    def apply(self, action: Action) -> None:
        self._apply_force_save("/api/v1/applications", action)
