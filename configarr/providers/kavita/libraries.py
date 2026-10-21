"""Kavita libraries, keyed by name. Client-free.

``GET /api/library/libraries`` lists the libraries the authenticated user can see
(an admin sees all of them — Kavita grants every new library to every admin).
``POST /api/library/create`` and ``POST /api/library/update`` both take an
``UpdateLibraryDto`` — the whole library, every field required — and
``DELETE /api/library/delete?libraryId=`` removes one, so libraries are prunable.
Deleting a library drops its series from Kavita's database (the files on disk are
not touched).

Over-current: a matched library keeps its current value for every field the config
does not set. A new library starts from the defaults Kavita's own UI uses, including
the file types and metadata provider that fit its ``type``. Kavita's create endpoint
ignores a few fields (``include_in_search``, and it forces scrobbling off for comic
libraries), so a create is followed by an update with the same body, so one run
converges.

Kavita serializes enums as integers; the config uses names (``type: light_novel``,
``file_group_types: [epub, pdf]``) and plans show names too.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable, Mapping
from typing import Any

from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.kavita.common import (
    FILE_TYPE_GROUPS,
    LIBRARY_TYPES,
    METADATA_PROVIDERS,
    enum_name,
    enum_value,
    kavita_session,
)

log = logging.getLogger(__name__)

# config key -> UpdateLibraryDto field (``name`` is the identity, set separately).
FIELDS: Mapping[str, str] = {
    "type": "type",
    "folders": "folders",
    "folder_watching": "folderWatching",
    "include_in_dashboard": "includeInDashboard",
    "include_in_search": "includeInSearch",
    "manage_collections": "manageCollections",
    "manage_reading_lists": "manageReadingLists",
    "allow_scrobbling": "allowScrobbling",
    "allow_metadata_matching": "allowMetadataMatching",
    "enable_metadata": "enableMetadata",
    "remove_prefix_for_sort_name": "removePrefixForSortName",
    "inherit_web_links_from_first_chapter": "inheritWebLinksFromFirstChapter",
    "default_language": "defaultLanguage",
    "metadata_provider": "metadataProvider",
    "file_group_types": "fileGroupTypes",
    "exclude_patterns": "excludePatterns",
}
# Fields compared as unordered sets (Kavita stores them as distinct rows).
_SET_FIELDS = frozenset({"folders", "fileGroupTypes", "excludePatterns"})

# A new library's defaults, as Kavita's library dialog sets them.
DEFAULTS: Mapping[str, Any] = {
    "folderWatching": True,
    "includeInDashboard": True,
    "includeInSearch": True,
    "manageCollections": False,
    "manageReadingLists": False,
    "allowScrobbling": True,
    "allowMetadataMatching": True,
    "enableMetadata": True,
    "removePrefixForSortName": False,
    "inheritWebLinksFromFirstChapter": False,
    "defaultLanguage": "",
    "excludePatterns": [],
}

_T = LIBRARY_TYPES
_F = FILE_TYPE_GROUPS
_M = METADATA_PROVIDERS
# File types Kavita's dialog preselects per library type.
DEFAULT_FILE_TYPES: Mapping[int, list[int]] = {
    _T["manga"]: [_F["archive"], _F["images"]],
    _T["comic"]: [_F["archive"]],
    _T["comic_vine"]: [_F["archive"]],
    _T["book"]: [_F["epub"], _F["pdf"]],
    _T["light_novel"]: [_F["epub"]],
    _T["image"]: [_F["images"]],
}
# Metadata providers Kavita accepts per library type (KavitaPlusConfiguration);
# the first is the default for a new library. Any other value fails the write.
VALID_METADATA_PROVIDERS: Mapping[int, list[int]] = {
    _T["manga"]: [_M["mangabaka"]],
    _T["comic"]: [_M["comic_book_roundup"], _M["hardcover"]],
    _T["comic_vine"]: [_M["comic_book_roundup"], _M["hardcover"]],
    _T["book"]: [_M["hardcover"], _M["mangabaka"]],
    _T["light_novel"]: [_M["mangabaka"], _M["hardcover"]],
    _T["image"]: [_M["mangabaka"], _M["comic_book_roundup"]],
}


def _from_current(lib: dict[str, Any]) -> dict[str, Any]:
    """A listed ``LibraryDto`` reshaped as the ``UpdateLibraryDto`` it would post."""
    obj = {field: lib.get(field) for field in FIELDS.values()}
    obj["fileGroupTypes"] = lib.get("libraryFileTypes") or []
    obj["id"] = lib.get("id")
    obj["name"] = lib.get("name")
    return obj


class KavitaLibraryProvider(CurrentStateCache):
    """Kavita libraries (create/update/delete), keyed by name."""

    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config: list[dict[str, Any]] = list(config or [])
        self._session = kavita_session(self.base_url, api_key)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/library/{path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        resp = self._session.get(self._url("libraries"))
        resp.raise_for_status()
        return [_from_current(lib) for lib in resp.json() or []]

    # -- plan ---------------------------------------------------------------
    def _wire(self, field: str, value: Any, name: str) -> Any:
        if field == "type":
            return enum_value(LIBRARY_TYPES, value, f"library type for '{name}'")
        if field == "metadataProvider":
            return enum_value(METADATA_PROVIDERS, value, f"metadata provider ({name})")
        if field == "fileGroupTypes":
            return [
                enum_value(FILE_TYPE_GROUPS, v, f"file group type ({name})")
                for v in value or []
            ]
        if field in ("folders", "excludePatterns"):
            return [str(v) for v in value or []]
        return value

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_name = {c["name"]: c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for entry in self.config:
            if not isinstance(entry, dict) or not entry.get("name"):
                raise ValueError("Kavita: every library needs a 'name'")
            name = str(entry["name"])
            unknown = sorted(k for k in entry if k != "name" and k not in FIELDS)
            if unknown:
                log.warning(
                    "Kavita library '%s': ignoring unknown setting(s): %s",
                    name,
                    ", ".join(unknown),
                )
            current = current_by_name.get(name)
            if current is None:
                for required in ("type", "folders"):
                    if not entry.get(required):
                        raise ValueError(
                            f"Kavita library '{name}' is missing required '{required}'"
                        )
                obj: dict[str, Any] = {"id": 0, **DEFAULTS, "name": name}
            else:
                obj = dict(current)
            for cfg_key, field in FIELDS.items():
                if entry.get(cfg_key) is not None:
                    obj[field] = self._wire(field, entry[cfg_key], name)

            lib_type = obj["type"]
            if current is None:
                if entry.get("file_group_types") is None:
                    obj["fileGroupTypes"] = list(DEFAULT_FILE_TYPES.get(lib_type, []))
                if (
                    lib_type == LIBRARY_TYPES["comic"]
                    and entry.get("allow_scrobbling") is None
                ):
                    obj["allowScrobbling"] = False  # Kavita forces this on create
            valid = VALID_METADATA_PROVIDERS.get(lib_type, [])
            if obj.get("metadataProvider") not in valid:
                if entry.get("metadata_provider") is not None:
                    raise ValueError(
                        f"Kavita library '{name}': metadata provider "
                        f"{enum_name(METADATA_PROVIDERS, obj['metadataProvider'])} "
                        f"is not valid for a {enum_name(LIBRARY_TYPES, lib_type)} "
                        "library (expected one of "
                        + ", ".join(
                            str(enum_name(METADATA_PROVIDERS, v)) for v in valid
                        )
                        + ")"
                    )
                # A new library, or a type change that invalidates the current one.
                obj["metadataProvider"] = valid[0] if valid else None
            desired.append(obj)
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field in FIELDS.values():
            value = resource.get(field)
            if field == "type":
                value = enum_name(LIBRARY_TYPES, value)
            elif field == "metadataProvider":
                value = enum_name(METADATA_PROVIDERS, value)
            elif field == "fileGroupTypes":
                value = sorted(str(enum_name(FILE_TYPE_GROUPS, v)) for v in value or [])
            elif field in _SET_FIELDS:
                value = sorted(str(v) for v in value or [])
            elif field == "defaultLanguage":
                value = value or ""
            else:
                value = coerce_scalar(value)
            out[field] = value
        return out

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        if plan.op is Op.CREATE:
            return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))
        assert current is not None, f"to_action: {plan.op!r} needs the current library"
        if plan.op is Op.DELETE:
            return Action(op=plan.op, key=plan.key, payload={"id": current["id"]})
        if plan.op is Op.UPDATE:
            return Action(
                op=plan.op,
                key=plan.key,
                payload={**(desired or {}), "id": current["id"]},
            )
        raise AssertionError(f"to_action: unexpected op {plan.op!r}")

    def apply(self, action: Action) -> int | None:
        body = dict(action.payload)
        library_id: int | None = None
        if action.op is Op.CREATE:
            resp = self._session.post(self._url("create"), json=body)
            resp.raise_for_status()
            created = resp.json() if resp.content else None
            if isinstance(created, dict) and isinstance(created.get("id"), int):
                library_id = created["id"]
                # Create ignores some fields (see module docstring); re-post them.
                resp = self._session.post(
                    self._url("update"), json={**body, "id": library_id}
                )
                resp.raise_for_status()
        elif action.op is Op.UPDATE:
            library_id = int(body["id"])
            resp = self._session.post(self._url("update"), json=body)
            resp.raise_for_status()
        elif action.op is Op.DELETE:
            resp = self._session.delete(
                self._url("delete"), params={"libraryId": body["id"]}
            )
            resp.raise_for_status()
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
        return library_id
