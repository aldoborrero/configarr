"""Root-folder provider for Bookshelf (Readarr). Client-free: talks HTTP via
requests.

Unlike Radarr/Sonarr, a Readarr root folder is more than a path: it carries a
display ``name`` and the defaults applied to authors added under it (quality and
metadata profile, monitoring options, tags), plus optional Calibre-library
settings. Readarr also supports ``PUT /rootfolder/{id}``, so this provider updates
those defaults in place instead of being create-only.

Matched by filesystem path (trailing slash ignored), which the server does not let
an update change. Full-replace: the PUT carries the whole object, so build_desired
merges the configured keys over current; unmanaged keys (the Calibre settings)
keep their server values. Profiles are referenced **by name** and resolved to ids
against ``/qualityprofile`` and ``/metadataprofile``. A name that does not exist
yet (a profile the same config creates earlier in the run) is kept as the name and
warned about during a plan; on apply it must resolve, since quality and metadata
profiles are synced before root folders. Not prunable: removing a library root is
left to a human.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any

from configarr.build import merge_full_replace
from configarr.plan import Op, ResourcePlan
from configarr.providers.arr.root_folders import _norm_path
from configarr.providers.base import Action, HttpProvider

log = logging.getLogger("configarr.bookshelf.root_folder")

# config key -> API field, for the plain passthrough keys.
_ENUM_FIELDS = {
    "default_monitor": "defaultMonitorOption",
    "default_new_item_monitor": "defaultNewItemMonitorOption",
}
# config key -> (API field, profile endpoint) for the by-name references.
_PROFILE_FIELDS = {
    "default_quality_profile": ("defaultQualityProfileId", "qualityprofile"),
    "default_metadata_profile": ("defaultMetadataProfileId", "metadataprofile"),
}
# Used only when creating a folder; an update keeps unset keys at their current
# server value via merge_full_replace. outputProfile must name a CalibreProfile
# even for a non-Calibre folder (the server validates it unconditionally).
_CREATE_DEFAULTS: dict[str, Any] = {
    "defaultMonitorOption": "all",
    "defaultNewItemMonitorOption": "all",
    "defaultTags": [],
    "isCalibreLibrary": False,
    "outputProfile": "default",
}
_COMPARED = (
    "name",
    "defaultQualityProfileId",
    "defaultMetadataProfileId",
    "defaultMonitorOption",
    "defaultNewItemMonitorOption",
)


class BookshelfRootFolderProvider(HttpProvider):
    """Diffs Bookshelf root folders by path; create and update (no prune)."""

    full_replace = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: Any,
        kind: str,
        api_prefix: str | None = "/api/v1",
    ):
        super().__init__(base_url, api_key, api_prefix)
        self.kind = kind
        self.config = config or []
        self._profile_cache: dict[str, dict[str, int]] = {}

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _norm_path(resource.get("path"))

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get(f"{self.api_prefix}/rootfolder").json()
        return data

    def _profile_ids(self, endpoint: str) -> dict[str, int]:
        if endpoint not in self._profile_cache:
            self._profile_cache[endpoint] = {
                p["name"]: p["id"]
                for p in self._get(f"{self.api_prefix}/{endpoint}").json()
            }
        return self._profile_cache[endpoint]

    def _resolve_profile(self, path: str, key: str, endpoint: str, value: Any) -> Any:
        """A profile reference (name, or a raw id) as the id the API wants. An
        unknown name stays a name during a plan (it may be created earlier in the
        same apply) and is an error on the apply path."""
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise ValueError(f"root folder {path!r}: invalid {key} {value!r}")
        if isinstance(value, int):
            return value
        ids = self._profile_ids(endpoint)
        if value in ids:
            return ids[value]
        # The runner turns this flag on only for the apply path (see HttpProvider).
        if self._create_missing_tags:
            raise ValueError(
                f"root folder {path!r}: {key} {value!r} does not exist on "
                f"{self.kind.split('.')[0]}"
            )
        log.warning(
            "root folder %r: %s %r does not exist on %s yet; it must be created "
            "before apply",
            path,
            key,
            value,
            self.kind.split(".")[0],
        )
        return value

    def _overrides(self, path: str, entry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"path": path}
        if "name" in entry:
            out["name"] = entry["name"]
        for cfg_key, api_field in _ENUM_FIELDS.items():
            if cfg_key in entry:
                value = entry[cfg_key]
                out[api_field] = value.lower() if isinstance(value, str) else value
        for cfg_key, (api_field, endpoint) in _PROFILE_FIELDS.items():
            if entry.get(cfg_key) is not None:
                out[api_field] = self._resolve_profile(
                    path, cfg_key, endpoint, entry[cfg_key]
                )
        if "default_tags" in entry:
            out["defaultTags"] = sorted(
                self._resolve_tags(entry["default_tags"]), key=str
            )
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_path = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for entry in self.config:
            path = _norm_path(entry.get("path"))
            if not path:
                raise ValueError(f"root folder entry without a 'path': {entry!r}")
            overrides = self._overrides(path, entry)
            current = current_by_path.get(path)
            if current is not None:
                desired.append(merge_full_replace({}, current, overrides))
                continue
            missing = [k for k in _PROFILE_FIELDS if entry.get(k) is None]
            if missing:
                raise ValueError(
                    f"root folder {path!r}: {' and '.join(missing)} required to "
                    "create it (Bookshelf needs both default profiles)"
                )
            # Bookshelf requires a name; default to the folder's last component.
            overrides.setdefault("name", path.rstrip("/").rsplit("/", 1)[-1] or path)
            desired.append({**_CREATE_DEFAULTS, **overrides})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Server stats (accessible/freeSpace/totalSpace) and the unmanaged Calibre
        # settings are never compared; they ride through the over-current merge.
        out: dict[str, Any] = {"path": _norm_path(resource.get("path"))}
        for field in _COMPARED:
            value = resource.get(field)
            out[field] = value.lower() if isinstance(value, str) else value
        # Restore the name's case (only enums are case-insensitive).
        out["name"] = resource.get("name")
        out["defaultTags"] = sorted(resource.get("defaultTags") or [], key=str)
        return out

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
        path = f"{self.api_prefix}/rootfolder"
        if action.op is Op.CREATE:
            self._post(path, json=action.payload)
        elif action.op is Op.UPDATE:
            self._put(f"{path}/{action.payload['id']}", json=action.payload)
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
