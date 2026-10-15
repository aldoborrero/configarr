"""Cleanuparr name-keyed collections: download clients and *arr instances.

Both are plain CRUD lists of objects with a GUID ``id`` and a unique ``name``:
POST to create, ``PUT .../{id}`` to update, ``DELETE .../{id}`` to remove (so both
are prunable). Each object is a handful of flat fields, mapped here from the
snake_case config key to the API field.

Over-current: a matched object keeps its current value for every field the config
does not set. Secrets (``apiKey``, ``password``) are echoed masked, so they are
left out of the diff; an update sends the configured secret when one is set and
the mask placeholder otherwise, which Cleanuparr treats as "keep the stored value".
A changed secret therefore does not show up in a plan on its own.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable, Mapping
from typing import Any, ClassVar

from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.cleanuparr.cleaner import NESTED_KEYS
from configarr.providers.cleanuparr.common import (
    SECRET_PLACEHOLDER,
    cleanuparr_session,
)
from configarr.providers.cleanuparr.sections import ARR_TYPES

log = logging.getLogger(__name__)

# (match key, config settings, identity fields) for one configured object.
Entry = tuple[Hashable, dict[str, Any], dict[str, Any]]


class _CleanuparrCollection(CurrentStateCache):
    """Shared plan/apply for a name-keyed Cleanuparr collection.

    Subclasses define ``FIELDS`` (config key -> API field), ``SECRETS`` (API fields
    that are masked), ``DEFAULTS`` for a new object, and ``_endpoint(resource)``.
    """

    prunable = True
    FIELDS: ClassVar[Mapping[str, str]] = {}
    SECRETS: ClassVar[frozenset[str]] = frozenset()
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}
    # Config keys owned by another provider (not warned about as unknown).
    NESTED: ClassVar[frozenset[str]] = frozenset()
    noun = "resource"

    def __init__(self, base_url: str, api_key: str, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self._session = cleanuparr_session(api_key)

    # -- subclass hooks -----------------------------------------------------
    def match_key(self, resource: dict[str, Any]) -> Hashable:
        raise NotImplementedError

    def _endpoint(self, resource: dict[str, Any]) -> str:
        raise NotImplementedError

    def _entries(self) -> list[Entry]:
        """(match key, config settings, identity fields) for every configured
        object."""
        raise NotImplementedError

    def _wire_value(self, field: str, value: Any) -> Any:
        return value

    def _compare_value(self, field: str, value: Any) -> Any:
        return coerce_scalar(value)

    # -- plan ---------------------------------------------------------------
    def build_desired(self) -> list[dict[str, Any]]:
        current_by_key = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for key, settings, identity in self._entries():
            unknown = sorted(
                k for k in settings if k not in self.FIELDS and k not in self.NESTED
            )
            if unknown:
                log.warning(
                    "Cleanuparr %s '%s': ignoring unknown setting(s): %s",
                    self.noun,
                    identity.get("name"),
                    ", ".join(unknown),
                )
            current = current_by_key.get(key)
            if current is None:
                obj = {**self.DEFAULTS, **identity}
            else:
                obj = {f: current.get(f) for f in self.FIELDS.values()}
                obj.update(identity)
                for secret in self.SECRETS:
                    obj[secret] = SECRET_PLACEHOLDER
            for cfg_key, field in self.FIELDS.items():
                if cfg_key in settings and settings[cfg_key] is not None:
                    obj[field] = self._wire_value(field, settings[cfg_key])
            desired.append(obj)
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return {
            field: self._compare_value(field, resource.get(field))
            for field in self.FIELDS.values()
            if field not in self.SECRETS
        }

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        if plan.op is Op.CREATE:
            return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))
        assert current is not None, f"to_action: {plan.op!r} needs the current object"
        if plan.op is Op.DELETE:
            return Action(op=plan.op, key=plan.key, payload=dict(current))
        if plan.op is Op.UPDATE:
            return Action(
                op=plan.op,
                key=plan.key,
                payload={**(desired or {}), "id": current["id"]},
            )
        raise AssertionError(f"to_action: unexpected op {plan.op!r}")

    def apply(self, action: Action) -> None:
        endpoint = self._endpoint(action.payload)
        body = {k: v for k, v in action.payload.items() if not k.startswith("_")}
        if action.op is Op.CREATE:
            resp = self._session.post(endpoint, json=body)
        elif action.op is Op.UPDATE:
            resp = self._session.put(f"{endpoint}/{body['id']}", json=body)
        elif action.op is Op.DELETE:
            resp = self._session.delete(f"{endpoint}/{body['id']}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()


# Cleanuparr's DownloadClientTypeName values, by their lowercase config spelling.
DOWNLOAD_CLIENT_TYPES: dict[str, str] = {
    "qbittorrent": "qBittorrent",
    "deluge": "Deluge",
    "transmission": "Transmission",
    "utorrent": "uTorrent",
    "rtorrent": "rTorrent",
    "sabnzbd": "Sabnzbd",
}


class CleanuparrDownloadClientProvider(_CleanuparrCollection):
    """Download clients (``/api/configuration/download_client``), keyed by name.

    ``type`` is required for a new client and cannot change afterwards (Cleanuparr
    locks it); a mismatch is an error rather than a delete-and-recreate.
    """

    noun = "download client"
    FIELDS: ClassVar[Mapping[str, str]] = {
        "enabled": "enabled",
        "type": "typeName",
        "host": "host",
        "username": "username",
        "password": "password",
        "api_key": "apiKey",
        "url_base": "urlBase",
        "external_url": "externalUrl",
        "download_directory_source": "downloadDirectorySource",
        "download_directory_target": "downloadDirectoryTarget",
    }
    SECRETS: ClassVar[frozenset[str]] = frozenset({"password", "apiKey"})
    DEFAULTS: ClassVar[Mapping[str, Any]] = {"enabled": True}
    # orphaned_files / unlinked / dead_torrent / seeding_rules (cleaner.py).
    NESTED: ClassVar[frozenset[str]] = NESTED_KEYS

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: dict[str, dict[str, Any]] = config or {}

    def _endpoint(self, resource: dict[str, Any]) -> str:
        return f"{self.base_url}/api/configuration/download_client"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        resp = self._session.get(self._endpoint({}))
        resp.raise_for_status()
        clients: list[dict[str, Any]] = (resp.json() or {}).get("clients", [])
        return clients

    def _entries(self) -> list[Entry]:
        current = {c.get("name"): c for c in self.fetch_current()}
        entries: list[Entry] = []
        for name, settings in self.config.items():
            settings = settings or {}
            existing = current.get(name)
            wanted = settings.get("type")
            if existing is None and not wanted:
                raise ValueError(
                    f"Cleanuparr download client '{name}' is missing required 'type'"
                )
            if (
                existing is not None
                and wanted
                and self._wire_value("typeName", wanted) != existing.get("typeName")
            ):
                raise ValueError(
                    f"Cleanuparr download client '{name}' is a "
                    f"{existing.get('typeName')}; its type cannot change to {wanted}"
                )
            entries.append((name, settings, {"name": name}))
        return entries

    def _wire_value(self, field: str, value: Any) -> Any:
        if field == "typeName":
            canonical = DOWNLOAD_CLIENT_TYPES.get(str(value).lower())
            if canonical is None:
                raise ValueError(
                    f"Cleanuparr: unknown download client type '{value}' "
                    f"(expected one of {', '.join(DOWNLOAD_CLIENT_TYPES)})"
                )
            return canonical
        return value


class CleanuparrArrInstanceProvider(_CleanuparrCollection):
    """*arr instances (``/api/configuration/<arr>/instances``), keyed by
    ``(arr type, name)`` across every arr type configured under ``arr:``.

    ``version`` is required for a new instance (Cleanuparr picks its API client by
    it). Cleanuparr stores ``url`` with a trailing slash, so URLs compare without
    one.
    """

    noun = "arr instance"
    FIELDS: ClassVar[Mapping[str, str]] = {
        "enabled": "enabled",
        "url": "url",
        "api_key": "apiKey",
        "version": "version",
        "external_url": "externalUrl",
    }
    SECRETS: ClassVar[frozenset[str]] = frozenset({"apiKey"})
    DEFAULTS: ClassVar[Mapping[str, Any]] = {"enabled": True}

    def __init__(self, base_url: str, api_key: str, arr: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: dict[str, dict[str, Any]] = {}
        for arr_type, body in (arr or {}).items():
            if arr_type not in ARR_TYPES:
                raise ValueError(
                    f"Cleanuparr: unknown arr type '{arr_type}' "
                    f"(expected one of {', '.join(ARR_TYPES)})"
                )
            instances = (body or {}).get("instances")
            if instances:
                self.config[arr_type] = instances

    def _endpoint(self, resource: dict[str, Any]) -> str:
        return f"{self.base_url}/api/configuration/{resource['_arr']}/instances"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource.get("_arr"), resource.get("name"))

    def _load_current(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for arr_type in self.config:
            resp = self._session.get(f"{self.base_url}/api/configuration/{arr_type}")
            resp.raise_for_status()
            for inst in (resp.json() or {}).get("instances", []):
                out.append({**inst, "_arr": arr_type})
        return out

    def _entries(self) -> list[Entry]:
        current = {self.match_key(c) for c in self.fetch_current()}
        entries: list[Entry] = []
        for arr_type, instances in self.config.items():
            for name, settings in instances.items():
                settings = settings or {}
                key = (arr_type, name)
                if key not in current:
                    for required in ("url", "api_key", "version"):
                        if settings.get(required) in (None, ""):
                            raise ValueError(
                                f"Cleanuparr {arr_type} instance '{name}' is missing "
                                f"required '{required}'"
                            )
                entries.append((key, settings, {"name": name, "_arr": arr_type}))
        return entries

    def _compare_value(self, field: str, value: Any) -> Any:
        if field == "url" and isinstance(value, str):
            return value.rstrip("/")
        if field == "version" and value is not None:
            return float(value)
        return coerce_scalar(value)
