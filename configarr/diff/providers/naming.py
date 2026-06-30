"""Naming / media-management provider (Radarr and Sonarr). Client-free: talks
HTTP via requests.

``/config/naming`` is a fixed-id singleton (no create/delete): GET the one object,
then PUT the whole object back. It is a full-replace resource, so build_desired
merges the config-derived overrides over current — unspecified keys keep their
server value instead of being reset by the PUT.

The two services share the endpoint but expose different field sets, and encode a
couple of fields differently: Radarr's ``colonReplacementFormat`` is a string while
Sonarr's is an int, and Sonarr adds ``multiEpisodeStyle`` (also an int). The
per-service maps below capture both the YAML->API field renames and those encodings.
"""

from __future__ import annotations

from typing import Any, Hashable

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.normalize import coerce_scalar
from configarr.diff.providers.base import Action, CurrentStateCache

_COLON_RADARR = {
    "delete": "delete",
    "dash": "dash",
    "spaceDash": "spaceDash",
    "spaceDashSpace": "spaceDashSpace",
    "smart": "smart",
}
_COLON_SONARR = {
    "delete": 0,
    "dash": 1,
    "spaceDash": 2,
    "spaceDashSpace": 3,
    "smart": 4,
}
_MULTI_EPISODE = {
    "extend": 0,
    "duplicate": 1,
    "repeat": 2,
    "scene": 3,
    "range": 5,
    "prefixedRange": 6,
}

# config key -> (API field, value mapping or None). The mapping translates the
# user-facing enum string into the encoding the API expects.
_SERVICE_FIELDS: dict[str, dict[str, tuple[str, dict[str, Any] | None]]] = {
    "radarr": {
        "rename_movies": ("renameMovies", None),
        "replace_illegal_characters": ("replaceIllegalCharacters", None),
        "colon_replacement": ("colonReplacementFormat", _COLON_RADARR),
        "standard_movie_format": ("standardMovieFormat", None),
        "movie_folder_format": ("movieFolderFormat", None),
    },
    "sonarr": {
        "rename_episodes": ("renameEpisodes", None),
        "replace_illegal_characters": ("replaceIllegalCharacters", None),
        "colon_replacement": ("colonReplacementFormat", _COLON_SONARR),
        "multi_episode_style": ("multiEpisodeStyle", _MULTI_EPISODE),
        "standard_episode_format": ("standardEpisodeFormat", None),
        "daily_episode_format": ("dailyEpisodeFormat", None),
        "anime_episode_format": ("animeEpisodeFormat", None),
        "series_folder_format": ("seriesFolderFormat", None),
        "season_folder_format": ("seasonFolderFormat", None),
        "specials_folder_format": ("specialsFolderFormat", None),
    },
}


class NamingProvider(CurrentStateCache):
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._fields = _SERVICE_FIELDS[kind.split(".")[0]]
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("id")

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/config/naming"))
        resp.raise_for_status()
        # Singleton: wrap the one object so the engine can index it like any list.
        return [resp.json()]

    def _overrides(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cfg_key, (api_field, mapping) in self._fields.items():
            if cfg_key not in self.config:
                continue
            value = self.config[cfg_key]
            if mapping is not None:
                value = mapping.get(value, value)
            out[api_field] = value
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        [current] = self.fetch_current()
        return [merge_full_replace({}, current, self._overrides())]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Allowlist the managed fields only; unmanaged server fields are carried
        # through the over-current merge, so they never produce a diff.
        return {
            api_field: coerce_scalar(resource.get(api_field))
            for api_field, _ in self._fields.values()
        }

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        naming_id = action.payload["id"]
        resp = self._session.put(
            self._url(f"/api/v3/config/naming/{naming_id}"), json=action.payload
        )
        resp.raise_for_status()
        self.invalidate_current()
