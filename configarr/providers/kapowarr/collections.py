"""Kapowarr collections: root folders, download clients and credentials.

All verified against Kapowarr V1.3.2 (``frontend/api.py`` and the backing
``backend/implementations/*``):

- **Root folders** (``/api/rootfolder``): ``POST {"folder"}`` / ``DELETE /{id}``.
  Kapowarr stores the folder with a trailing ``/``, so paths match without one.
  The folder must exist in the container and may not overlap the download
  folder or another root folder. Keyed by path; prunable.
- **Download clients** (``/api/externalclients``, the "external" torrent
  clients): keyed by ``title``. ``POST`` takes ``download_type`` (2 = torrent),
  ``client_type``, ``title``, ``enabled``, ``base_url``, ``username``,
  ``password``, ``api_token``; ``PUT /{id}`` is full-replace over ``title``,
  ``enabled``, ``base_url`` and the credentials (a field the client type does not
  use is stored as null), so an update carries the current values for everything
  the config leaves out. Kapowarr connects to the client on every add/update and
  rejects the write if it can't. Credentials come back in clear text and are
  compared by fingerprint. ``client_type`` cannot change. Prunable.
- **Credentials** (``/api/credentials``, logins for direct-download services):
  keyed by ``source`` (``mega``: ``email`` + ``password``; ``pixeldrain``:
  ``api_key``). There is no update endpoint, so a change is a new credential
  followed by deleting the old one. ``password`` is echoed masked and not diffed.
  Prunable.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable, Mapping
from typing import Any, ClassVar

from configarr.normalize import coerce_scalar, redact_secret_fields
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action
from configarr.providers.kapowarr.common import KapowarrProvider, norm_base_url

log = logging.getLogger(__name__)


def _norm_path(path: Any) -> str | None:
    if not isinstance(path, str):
        return None
    return path.rstrip("/") or "/"


class _Collection(KapowarrProvider):
    """Shared to_action for an id-addressed Kapowarr collection."""

    prunable = True

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
            return Action(op=plan.op, key=plan.key, payload={"id": current["id"]})
        if plan.op is Op.UPDATE:
            return Action(
                op=plan.op,
                key=plan.key,
                payload={**(desired or {}), "id": current["id"]},
            )
        raise AssertionError(f"to_action: unexpected op {plan.op!r}")


class KapowarrRootFolderProvider(_Collection):
    """Root folders keyed by path; create/delete only (a path change is a new
    folder)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: list[dict[str, Any]] = list(config or [])

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _norm_path(resource.get("folder"))

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return list(self._get("/rootfolder") or [])

    def build_desired(self) -> list[dict[str, Any]]:
        return [
            {"folder": _norm_path(entry["path"])}
            for entry in self.config
            if entry.get("path")
        ]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return {"folder": _norm_path(resource.get("folder"))}

    def apply(self, action: Action) -> int | None:
        service_id = None
        if action.op is Op.CREATE:
            created = self._call("POST", "/rootfolder", json=action.payload) or {}
            service_id = created.get("id")
        elif action.op is Op.DELETE:
            self._call("DELETE", f"/rootfolder/{action.payload['id']}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
        return service_id


# Kapowarr's external client types (V1.3.2: both torrent) -> (spelling, download_type).
CLIENT_TYPES: dict[str, tuple[str, int]] = {
    "transmission": ("Transmission", 2),
    "qbittorrent": ("qBittorrent", 2),
}


class KapowarrDownloadClientProvider(_Collection):
    """External download clients (``/api/externalclients``), keyed by title."""

    FIELDS: ClassVar[tuple[str, ...]] = (
        "enabled",
        "base_url",
        "username",
        "password",
        "api_token",
    )
    CONFIG_KEYS: ClassVar[frozenset[str]] = frozenset({*FIELDS, "client_type"})

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: dict[str, dict[str, Any]] = dict(config or {})

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("title")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return list(self._get("/externalclients") or [])

    @staticmethod
    def _client_type(title: str, value: Any) -> tuple[str, int]:
        found = CLIENT_TYPES.get(str(value).lower())
        if found is None:
            raise ValueError(
                f"Kapowarr download client '{title}': unknown client_type '{value}' "
                f"(expected one of {', '.join(c for c, _ in CLIENT_TYPES.values())})"
            )
        return found

    def build_desired(self) -> list[dict[str, Any]]:
        current = {c.get("title"): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for title, settings in self.config.items():
            settings = settings or {}
            unknown = sorted(k for k in settings if k not in self.CONFIG_KEYS)
            if unknown:
                log.warning(
                    "Kapowarr download client '%s': ignoring unknown setting(s): %s",
                    title,
                    ", ".join(unknown),
                )
            existing = current.get(title)
            wanted = settings.get("client_type")
            if existing is None:
                if not wanted or not settings.get("base_url"):
                    raise ValueError(
                        f"Kapowarr download client '{title}' needs 'client_type' "
                        "and 'base_url' to be created"
                    )
                client_type, download_type = self._client_type(title, wanted)
                obj: dict[str, Any] = {
                    "download_type": download_type,
                    "client_type": client_type,
                    "title": title,
                    "enabled": True,
                    "username": None,
                    "password": None,
                    "api_token": None,
                }
            else:
                if wanted and self._client_type(title, wanted)[0] != existing.get(
                    "client_type"
                ):
                    raise ValueError(
                        f"Kapowarr download client '{title}' is a "
                        f"{existing.get('client_type')}; its client_type cannot "
                        f"change to {wanted}"
                    )
                obj = {"client_type": existing.get("client_type"), "title": title}
                obj.update({f: existing.get(f) for f in self.FIELDS})
            for field in self.FIELDS:
                if field in settings:
                    obj[field] = settings[field]
            desired.append(obj)
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return redact_secret_fields(
            {
                "client_type": resource.get("client_type"),
                "enabled": coerce_scalar(resource.get("enabled")),
                "base_url": norm_base_url(resource.get("base_url")),
                "username": resource.get("username") or None,
                "password": resource.get("password") or None,
                "api_token": resource.get("api_token") or None,
            }
        )

    def apply(self, action: Action) -> int | None:
        body = dict(action.payload)
        service_id = body.get("id")
        if action.op is Op.CREATE:
            created = self._call("POST", "/externalclients", json=body) or {}
            service_id = created.get("id")
        elif action.op is Op.UPDATE:
            put = {k: body.get(k) for k in ("title", *self.FIELDS)}
            self._call("PUT", f"/externalclients/{service_id}", json=put)
        elif action.op is Op.DELETE:
            self._call("DELETE", f"/externalclients/{service_id}")
            service_id = None
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
        return service_id


# Credential source -> the fields its validator keeps (others are stored null).
CREDENTIAL_FIELDS: Mapping[str, tuple[str, ...]] = {
    "mega": ("email", "password"),
    "pixeldrain": ("api_key",),
}


class KapowarrCredentialProvider(_Collection):
    """Download-service credentials (``/api/credentials``), keyed by source.

    Kapowarr allows several credentials per source; configarr manages one, so a
    server with two for the same source is reported as an identity clash.
    """

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key, kind)
        self.config: dict[str, dict[str, Any]] = {}
        for source, settings in (config or {}).items():
            source = str(source).lower()
            if source not in CREDENTIAL_FIELDS:
                raise ValueError(
                    f"Kapowarr credentials: unknown source '{source}' "
                    f"(expected one of {', '.join(CREDENTIAL_FIELDS)})"
                )
            self.config[source] = settings or {}

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("source")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        return list(self._get("/credentials") or [])

    def build_desired(self) -> list[dict[str, Any]]:
        desired: list[dict[str, Any]] = []
        for source, settings in self.config.items():
            fields = CREDENTIAL_FIELDS[source]
            unknown = sorted(k for k in settings if k not in fields)
            if unknown:
                log.warning(
                    "Kapowarr credential '%s': ignoring unknown setting(s): %s",
                    source,
                    ", ".join(unknown),
                )
            missing = [f for f in fields if settings.get(f) in (None, "")]
            if missing:
                raise ValueError(
                    f"Kapowarr credential '{source}' is missing required "
                    f"{', '.join(repr(m) for m in missing)}"
                )
            desired.append({"source": source, **{f: settings[f] for f in fields}})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        fields = CREDENTIAL_FIELDS.get(str(resource.get("source")), ())
        return redact_secret_fields(
            {f: resource.get(f) for f in fields if f != "password"}
        )

    def apply(self, action: Action) -> int | None:
        body = dict(action.payload)
        service_id: int | None = None
        if action.op in (Op.CREATE, Op.UPDATE):
            # No PUT: create the new credential first, then drop the old one, so a
            # rejected login leaves the stored credential in place.
            new = {k: v for k, v in body.items() if k != "id"}
            created = self._call("POST", "/credentials", json=new) or {}
            service_id = created.get("id")
            if action.op is Op.UPDATE:
                self._call("DELETE", f"/credentials/{body['id']}")
        elif action.op is Op.DELETE:
            self._call("DELETE", f"/credentials/{body['id']}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
        return service_id
