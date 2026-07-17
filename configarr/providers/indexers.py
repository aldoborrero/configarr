"""Indexer provider for Prowlarr. Client-free: talks HTTP via requests.

Provider-Field resource (rollout work-list #9): the object carries a ``fields``
list whose shape comes from ``/indexer/schema``. Prowlarr uses the ``/api/v1``
base path. Full-replace + over current: a matched indexer keeps its server field
values, with only the configured ``settings`` overlaid, so an apply never resets
fields the user did not set. A new indexer is built from the schema defaults.

Generic implementations (Newznab, Torznab) resolve their schema by implementation,
but every Cardigann site shares ``implementation="Cardigann"``, so a specific site
is selected by its schema ``name`` via the optional ``definition`` config key.
``appProfileId`` and ``redirect`` are indexer-only. Secret fields (apiKey/password)
are echoed masked, so they are skipped from the diff by name (apply still sends the
real value). PUT/POST pass ``forceSave=true`` to skip the live connectivity test.
"""

from __future__ import annotations

from typing import Any

from configarr.build import merge_full_replace
from configarr.normalize import coerce_scalar
from configarr.providers.base import Action, FieldProvider


class IndexerProvider(FieldProvider):
    """Diffs Prowlarr indexers by name (provider-Field resource)."""

    _tag_path = "/api/v1/tag"
    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key, config, kind)
        # (by implementation, by schema name) — built together, cached.
        self._schema_cache: (
            tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]] | None
        ) = None

    def _schemas(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if self._schema_cache is None:
            by_impl: dict[str, dict[str, Any]] = {}
            by_name: dict[str, dict[str, Any]] = {}
            for s in self._get("/api/v1/indexer/schema").json():
                impl = s.get("implementation")
                # First schema per implementation wins (matches generic indexers).
                if impl and impl not in by_impl:
                    by_impl[impl] = s
                if s.get("name"):
                    by_name[s["name"]] = s
            self._schema_cache = (by_impl, by_name)
        return self._schema_cache

    def _schema_for(
        self, implementation: str, definition: str | None
    ) -> dict[str, Any]:
        by_impl, by_name = self._schemas()
        if definition:
            # Fail fast on a typo'd definition — otherwise an empty schema is built
            # and the indexer POST 400s server-side with an opaque error.
            if definition not in by_name:
                raise ValueError(
                    f"unknown Prowlarr indexer definition {definition!r} "
                    "(not in /api/v1/indexer/schema)"
                )
            return by_name[definition]
        if implementation not in by_impl:
            raise ValueError(
                f"unknown Prowlarr indexer implementation {implementation!r}"
            )
        return by_impl[implementation]

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v1/indexer").json()
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
                "priority": definition.get("priority", 25),
                "appProfileId": definition.get("app_profile_id", 1),
                "redirect": definition.get("redirect", False),
                "tags": self._resolve_tags(definition.get("tags")),
            }
            current = current_by_key.get(name)
            if current is None:
                impl = definition.get("implementation")
                if not impl:
                    raise ValueError(f"Missing 'implementation' for indexer: {name}")
                schema = self._schema_for(impl, definition.get("definition"))
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
            "priority": coerce_scalar(resource.get("priority", 25)),
            "appProfileId": coerce_scalar(resource.get("appProfileId", 1)),
            "redirect": bool(resource.get("redirect", False)),
            "implementation": resource.get("implementation"),
            "configContract": resource.get("configContract"),
            "protocol": resource.get("protocol"),
            "tags": sorted(resource.get("tags") or []),
            "fields": self._normalized_fields(resource),
        }

    def apply(self, action: Action) -> int | None:
        return self._apply_force_save("/api/v1/indexer", action)
