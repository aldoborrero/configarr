"""Seerr DVR-instance providers (Radarr/Sonarr registrations inside Seerr).
Client-free: talks HTTP via requests.

Seerr stores the *arr instances it dispatches requests to under
``/api/v1/settings/radarr`` and ``/api/v1/settings/sonarr``: a JSON array of
objects with a server-assigned ``id`` and a user-chosen ``name``. Instances are
created with ``POST /api/v1/settings/<kind>``, updated with
``PUT /api/v1/settings/<kind>/{id}`` and removed with ``DELETE``. This provider
diffs them by ``name`` — the only stable user-facing identity, since ``id`` is
assigned on create.

Three behaviours of Seerr's API shape this module:

- **The write routes do not validate.** Both handlers do ``req.body as
  RadarrSettings`` — a bare TypeScript cast — and persist the object verbatim, so
  a misspelled key is *stored* (and then ignored by every consumer) and a missing
  one is simply absent rather than defaulted. Every key is therefore built from the
  allow-lists below, with Seerr's own UI defaults filled in, and a configured key
  outside the allow-list is a hard error.
- **Seerr wants a quality profile by id *and* by name** (``activeProfileId`` +
  ``activeProfileName``) and looks up neither. The config takes a profile *name*,
  and the ids come from ``POST /api/v1/settings/<kind>/test`` — the same
  connection probe Seerr's own modal uses, which returns the target *arr's quality
  profiles, root folders and tags. Going through Seerr rather than straight to the
  *arr is deliberate: what has to be reachable is Seerr, not configarr.
- **``seerr-api.yml`` lags the code.** The published OpenAPI spec (and therefore
  the generated ``seerr`` Python client) is missing ``tags``, ``tagRequests``,
  ``seriesType``, ``animeSeriesType``, ``animeTags``, ``monitorNewItems`` and
  ``overrideRule``. The allow-lists here follow ``DVRSettings`` /
  ``RadarrSettings`` / ``SonarrSettings`` in ``server/lib/settings``, and the
  defaults and enum values follow the ``RadarrModal`` / ``SonarrModal`` forms.

Not managed: ``overrideRule`` (Seerr's separate override-rule resource) and the
``activeLanguageProfileId`` pair (Sonarr v3 only — Seerr's probe returns language
profiles solely for major version ≤ 3).

Auth: Seerr's ``X-Api-Key`` resolves to user id 1 (the owner). Until the setup
wizard has created that owner, every ``/api/v1/settings/*`` route answers 403 —
surfaced as a clear error rather than self-healed, so a plan stays read-only.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any, ClassVar

import requests

from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.transport import build_session

log = logging.getLogger(__name__)

# YAML key -> Seerr payload key, for the settings shared by both kinds.
_COMMON_FIELDS: dict[str, str] = {
    "hostname": "hostname",
    "port": "port",
    "api_key": "apiKey",
    "use_ssl": "useSsl",
    "base_url": "baseUrl",
    "is_4k": "is4k",
    "is_default": "isDefault",
    "external_url": "externalUrl",
    "sync_enabled": "syncEnabled",
    "prevent_search": "preventSearch",
    "tag_requests": "tagRequests",
}
_RADARR_FIELDS: dict[str, str] = {"minimum_availability": "minimumAvailability"}
_SONARR_FIELDS: dict[str, str] = {
    "season_folders": "enableSeasonFolders",
    "series_type": "seriesType",
    "anime_series_type": "animeSeriesType",
    "monitor_new_items": "monitorNewItems",
}

# Resolved from a name to an id/name pair against the target *arr.
_PROFILE_KEYS = ("quality_profile", "anime_quality_profile")
_FOLDER_KEYS = ("root_folder", "anime_root_folder")
# Tag lists, which accept a label or an id. YAML key -> Seerr payload key.
_COMMON_TAG_FIELDS: dict[str, str] = {"tags": "tags"}
_SONARR_TAG_FIELDS: dict[str, str] = {"anime_tags": "animeTags"}

# The <select> options in Seerr's own modals. The routes cast rather than
# validate, so an invalid value is stored and only breaks at request time.
_ENUMS: dict[str, tuple[str, ...]] = {
    "minimum_availability": ("announced", "inCinemas", "released"),
    "series_type": ("standard", "daily"),
    "anime_series_type": ("anime", "standard"),
    "monitor_new_items": ("all", "none"),
}

_COMMON_DEFAULTS: dict[str, Any] = {
    "useSsl": False,
    "baseUrl": "",
    "is4k": False,
    "isDefault": False,
    "externalUrl": "",
    "syncEnabled": False,
    "preventSearch": False,
    "tags": [],
    "tagRequests": False,
}


class _Probe:
    """What Seerr's connection test reports about one target *arr."""

    __slots__ = ("folders", "profiles", "tags")

    def __init__(
        self, profiles: dict[str, int], folders: set[str], tags: dict[str, int]
    ) -> None:
        self.profiles = profiles
        self.folders = folders
        self.tags = tags


class SeerrDvrProvider(CurrentStateCache):
    """Diffs the Radarr/Sonarr instances registered inside Seerr, by name."""

    # Set by the subclasses.
    api_path: str = ""
    default_port: int = 0
    extra_fields: ClassVar[dict[str, str]] = {}
    extra_tag_fields: ClassVar[dict[str, str]] = {}
    extra_defaults: ClassVar[dict[str, Any]] = {}
    supports_anime: bool = False
    prunable = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or {}
        self._session = build_session()
        self._session.headers["X-Api-Key"] = api_key
        # name -> probe result per target *arr, fetched at most once.
        self._probe_cache: dict[str, _Probe] = {}

    # --- identity -----------------------------------------------------------

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    # --- Seerr HTTP ---------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _owner_error(self) -> RuntimeError:
        return RuntimeError(
            f"Seerr returned 403 for {self.api_path}. Its API key maps to the "
            "owner account (user id 1); complete Seerr's setup wizard once so "
            "that account exists, then re-run."
        )

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url(self.api_path))
        if resp.status_code == 403:
            raise self._owner_error()
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    # --- target *arr lookups ------------------------------------------------

    def _probe(self, name: str, settings: dict[str, Any]) -> _Probe:
        """Ask Seerr to connect to the *arr this instance points at and report its
        quality profiles, root folders and tags."""
        if name in self._probe_cache:
            return self._probe_cache[name]
        body = {
            "hostname": settings["hostname"],
            "port": settings.get("port", self.default_port),
            "apiKey": settings["api_key"],
            "useSsl": bool(settings.get("use_ssl", False)),
            "baseUrl": settings.get("base_url", ""),
        }
        try:
            resp = self._session.post(self._url(f"{self.api_path}/test"), json=body)
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Seerr instance {name!r}: probe failed ({exc})"
            ) from exc
        if resp.status_code == 403:
            raise self._owner_error()
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Seerr instance {name!r}: Seerr cannot reach its *arr at "
                f"{body['hostname']}:{body['port']} "
                f"(HTTP {resp.status_code}: {resp.text.strip()[:200]})"
            )
        data = resp.json()
        probe = _Probe(
            profiles={p["name"]: p["id"] for p in data.get("profiles", [])},
            folders={f["path"] for f in data.get("rootFolders", [])},
            tags={t["label"]: t["id"] for t in data.get("tags", [])},
        )
        self._probe_cache[name] = probe
        return probe

    # --- desired state ------------------------------------------------------

    def _managed_yaml_keys(self) -> frozenset[str]:
        keys = {
            *_COMMON_FIELDS,
            *self.extra_fields,
            *_COMMON_TAG_FIELDS,
            *self.extra_tag_fields,
            "quality_profile",
            "root_folder",
        }
        if self.supports_anime:
            keys |= {"anime_quality_profile", "anime_root_folder"}
        return frozenset(keys)

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        managed = self._managed_yaml_keys()
        desired: list[dict[str, Any]] = []
        for name, raw in self.config.items():
            settings = dict(raw or {})
            for required in ("hostname", "api_key", "quality_profile", "root_folder"):
                if not settings.get(required):
                    raise ValueError(
                        f"Seerr {self.kind} instance '{name}' is missing required "
                        f"'{required}'"
                    )
            unknown = sorted(k for k in settings if k not in managed)
            if unknown:
                raise ValueError(
                    f"Seerr {self.kind} instance '{name}': unknown setting(s) "
                    f"{', '.join(unknown)}"
                )
            self._check_enums(name, settings)
            probe = self._probe(name, settings)
            payload: dict[str, Any] = {
                "name": name,
                "port": settings.get("port", self.default_port),
                **_COMMON_DEFAULTS,
                **self.extra_defaults,
            }
            for yaml_key, api_key in {**_COMMON_FIELDS, **self.extra_fields}.items():
                if yaml_key in settings:
                    payload[api_key] = settings[yaml_key]
            tag_fields = {**_COMMON_TAG_FIELDS, **self.extra_tag_fields}
            for yaml_key, api_key in tag_fields.items():
                if yaml_key in settings:
                    payload[api_key] = self._resolve_tags(
                        name, yaml_key, settings[yaml_key], probe
                    )
            payload.update(self._resolve_pair(name, settings, probe, anime=False))
            if self.supports_anime:
                payload.update(self._resolve_pair(name, settings, probe, anime=True))
            desired.append(payload)
        return desired

    def _check_enums(self, name: str, settings: dict[str, Any]) -> None:
        for key, allowed in _ENUMS.items():
            if key in settings and settings[key] not in allowed:
                raise ValueError(
                    f"Seerr {self.kind} instance '{name}': {key} must be one of "
                    f"{', '.join(allowed)} (got {settings[key]!r})"
                )

    def _resolve_tags(
        self, name: str, key: str, value: Any, probe: _Probe
    ) -> list[int]:
        """Tags may be written as ids or as the labels shown in the *arr."""
        if not isinstance(value, list):
            raise ValueError(
                f"Seerr {self.kind} instance '{name}': {key} must be a list of tag "
                f"labels or ids (got {value!r})"
            )
        resolved: list[int] = []
        for item in value:
            if isinstance(item, bool):
                raise ValueError(
                    f"Seerr {self.kind} instance '{name}': {key} entry {item!r} is "
                    "not a tag label or id"
                )
            if isinstance(item, int):
                resolved.append(item)
                continue
            if item not in probe.tags:
                raise ValueError(
                    f"Seerr {self.kind} instance '{name}': tag {item!r} does not "
                    f"exist on the target *arr "
                    f"(available: {', '.join(sorted(probe.tags)) or 'none'})"
                )
            resolved.append(probe.tags[item])
        return resolved

    def _resolve_pair(
        self,
        name: str,
        settings: dict[str, Any],
        probe: _Probe,
        *,
        anime: bool,
    ) -> dict[str, Any]:
        """The ``activeProfileId``/``activeProfileName``/``activeDirectory`` trio
        (or its anime counterpart) for one instance."""
        prefix = "anime_" if anime else ""
        profile = settings.get(f"{prefix}quality_profile")
        folder = settings.get(f"{prefix}root_folder")
        if anime and profile is None and folder is None:
            return {}
        if profile is not None and profile not in probe.profiles:
            raise ValueError(
                f"Seerr {self.kind} instance '{name}': quality profile "
                f"{profile!r} does not exist on the target *arr "
                f"(available: {', '.join(sorted(probe.profiles)) or 'none'})"
            )
        if folder is not None and folder not in probe.folders:
            raise ValueError(
                f"Seerr {self.kind} instance '{name}': root folder {folder!r} is "
                f"not configured on the target *arr "
                f"(available: {', '.join(sorted(probe.folders)) or 'none'})"
            )
        assert isinstance(profile, str), "a resolved profile is always a name"
        if anime:
            return {
                "activeAnimeProfileId": probe.profiles[profile],
                "activeAnimeProfileName": profile,
                "activeAnimeDirectory": folder,
            }
        return {
            "activeProfileId": probe.profiles[profile],
            "activeProfileName": profile,
            "activeDirectory": folder,
        }

    # --- diff ---------------------------------------------------------------

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Compare only the keys this provider manages; Seerr echoes extras (``id``,
        ``overrideRule``, and on older instances fields it no longer writes) that
        must not show as drift."""
        managed = {
            "name",
            *_COMMON_FIELDS.values(),
            *self.extra_fields.values(),
            *_COMMON_TAG_FIELDS.values(),
            *self.extra_tag_fields.values(),
            "activeProfileId",
            "activeProfileName",
            "activeDirectory",
        }
        if self.supports_anime:
            managed |= {
                "activeAnimeProfileId",
                "activeAnimeProfileName",
                "activeAnimeDirectory",
            }
        out: dict[str, Any] = {}
        for key in sorted(managed):
            if key not in resource or resource[key] is None:
                continue
            value = resource[key]
            out[key] = (
                sorted(value) if isinstance(value, list) else coerce_scalar(value)
            )
        return out

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        if plan.op is Op.DELETE:
            assert current is not None, "to_action: DELETE without a current resource"
            return Action(op=plan.op, key=plan.key, payload={"id": current["id"]})
        payload = dict(desired or {})
        if plan.op is Op.UPDATE:
            assert current is not None, "to_action: UPDATE without a current resource"
            payload["id"] = current["id"]
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> int | None:
        if action.op is Op.CREATE:
            resp = self._session.post(self._url(self.api_path), json=action.payload)
        elif action.op is Op.UPDATE:
            payload = dict(action.payload)
            instance_id = payload.pop("id")
            resp = self._session.put(
                self._url(f"{self.api_path}/{instance_id}"), json=payload
            )
        elif action.op is Op.DELETE:
            resp = self._session.delete(
                self._url(f"{self.api_path}/{action.payload['id']}")
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
        if action.op is Op.DELETE:
            return None
        body = resp.json() if resp.content else {}
        return body.get("id") if isinstance(body, dict) else None


class SeerrRadarrProvider(SeerrDvrProvider):
    """Radarr instances registered inside Seerr."""

    api_path = "/settings/radarr"
    default_port = 7878
    extra_fields: ClassVar[dict[str, str]] = _RADARR_FIELDS
    extra_defaults: ClassVar[dict[str, Any]] = {"minimumAvailability": "released"}


class SeerrSonarrProvider(SeerrDvrProvider):
    """Sonarr instances registered inside Seerr, including the anime profile pair."""

    api_path = "/settings/sonarr"
    default_port = 8989
    extra_fields: ClassVar[dict[str, str]] = _SONARR_FIELDS
    extra_tag_fields: ClassVar[dict[str, str]] = _SONARR_TAG_FIELDS
    extra_defaults: ClassVar[dict[str, Any]] = {
        "enableSeasonFolders": False,
        "seriesType": "standard",
        "animeSeriesType": "anime",
        "monitorNewItems": "all",
    }
    supports_anime = True
