"""Import-list provider (Radarr and Sonarr share the ``/api/v3/importlist`` API).
Client-free: talks HTTP via requests.

Provider-Field resource, like download clients: the object carries a schema-driven
``fields`` list (per implementation) plus a set of top-level attributes. Those
top-level attributes **differ by service** (Radarr has ``enabled``/``enableAuto``/
``monitor``/``minimumAvailability``; Sonarr has ``enableAutomaticAdd``/``seasonFolder``/
``seriesType``/…), so rather than model a fixed set this provider passes the
top-level keys the user writes straight through to the API (matching the
``settings:``/fields passthrough philosophy) and normalizes against a superset of
both services' fields — the absent service's fields are simply not present on
either side, so they never produce a diff.

Full-replace + over current: a matched list keeps its server values, with only the
configured top-level keys and ``settings`` overlaid. apiKey/secret fields are echoed
masked and skipped from the diff by name. Writes pass ``forceSave=true`` to skip the
list's live fetch test.
"""

from __future__ import annotations

from typing import Any

from configarr.build import merge_full_replace
from configarr.normalize import coerce_scalar
from configarr.providers.base import Action, FieldProvider

# Superset of the user-settable top-level fields across Radarr and Sonarr import
# lists (camelCase API names). Only those present on a given resource are compared.
_TOP_FIELDS = (
    "implementation",
    "configContract",
    "enabled",
    "enableAuto",
    "enableAutomaticAdd",
    "monitor",
    "shouldMonitor",
    "monitorNewItems",
    "searchOnAdd",
    "searchForMissingEpisodes",
    "rootFolderPath",
    "qualityProfileId",
    "minimumAvailability",
    "seriesType",
    "seasonFolder",
)
# Keys handled specially in a definition; everything else is a top-level API field.
_SPECIAL = frozenset({"settings", "tags"})


class ImportListProvider(FieldProvider):
    """Diffs Radarr/Sonarr import lists by name (provider-Field resource)."""

    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key, config, kind)
        self._schema_cache: dict[str, dict[str, Any]] | None = None

    def _schema(self) -> dict[str, dict[str, Any]]:
        if self._schema_cache is None:
            self._schema_cache = {
                s["implementation"]: s
                for s in self._get("/api/v3/importlist/schema").json()
            }
        return self._schema_cache

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/importlist").json()
        return data

    def build_desired(self) -> list[dict[str, Any]]:
        self._secret_names_ready = True
        if not self.config:
            return []
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, definition in self.config.items():
            settings = definition.get("settings") or {}
            # Every non-special key is a top-level API field passed straight through.
            top_level = {k: v for k, v in definition.items() if k not in _SPECIAL}
            overrides: dict[str, Any] = {
                **top_level,
                "name": name,
                "tags": self._resolve_tags(definition.get("tags")),
            }
            current = current_by_key.get(name)
            if current is None:
                impl = definition.get("implementation")
                if not impl:
                    raise ValueError(
                        f"Missing 'implementation' for import list: {name}"
                    )
                schema = self._schema().get(impl, {})
                desired.append(
                    {
                        **overrides,
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
        out: dict[str, Any] = {
            field: coerce_scalar(resource.get(field))
            for field in _TOP_FIELDS
            if field in resource
        }
        out["tags"] = sorted(resource.get("tags") or [])
        out["fields"] = self._normalized_fields(resource)
        return out

    def apply(self, action: Action) -> int | None:
        return self._apply_force_save("/api/v3/importlist", action)
