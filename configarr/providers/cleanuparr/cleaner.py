"""Cleanuparr download-cleaner settings that hang off one download client.

Configured under ``download_clients.<name>`` next to the client's own fields:

- ``orphaned_files``, ``unlinked``, ``dead_torrent`` — one settings object per
  client, written with ``PUT /api/{orphaned-files,unlinked,dead-torrent}-config/
  {clientId}`` (full-replace, so merged over the current object like the sections);
- ``seeding_rules`` — a name-keyed list per client: ``POST /api/seeding-rules/
  {clientId}`` to create, ``PUT``/``DELETE /api/seeding-rules/{id}``.

All of it is read in one ``GET /api/configuration/download_cleaner`` (its
``clients[]`` carry every per-client config). A client created in the same run has
no id at plan time; apply resolves it by name.

Not every client type supports every setting (Cleanuparr's capability table:
usenet clients only have the orphaned-files scanner; ``dead_torrent`` needs a
seeders-capable torrent client), so an unsupported one fails at plan time with a
clear error instead of a 400 at apply.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any

from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.cleanuparr.common import (
    cleanuparr_session,
    flatten,
    merge_over,
    to_wire,
)

log = logging.getLogger(__name__)

# config key -> (field in download_cleaner.clients[], PUT path prefix)
CLIENT_SETTINGS: dict[str, tuple[str, str]] = {
    "orphaned_files": ("orphanedFilesConfig", "orphaned-files-config"),
    "unlinked": ("unlinkedConfig", "unlinked-config"),
    "dead_torrent": ("deadTorrentConfig", "dead-torrent-config"),
}
NESTED_KEYS = frozenset({*CLIENT_SETTINGS, "seeding_rules"})

# Which nested settings each client type supports (Cleanuparr's
# DownloadClientCapabilities: Usenet = orphan claims only; rTorrent lacks the
# seeders filtering dead-torrent needs).
_TORRENT = frozenset({"orphaned_files", "unlinked", "seeding_rules"})
SUPPORTED: dict[str, frozenset[str]] = {
    "qbittorrent": _TORRENT | {"dead_torrent"},
    "deluge": _TORRENT | {"dead_torrent"},
    "transmission": _TORRENT | {"dead_torrent"},
    "utorrent": _TORRENT | {"dead_torrent"},
    "rtorrent": _TORRENT,
    "sabnzbd": frozenset({"orphaned_files"}),
}

_READ_ONLY = frozenset({"id", "downloadClientConfigId"})


def _strip(obj: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (obj or {}).items() if k not in _READ_ONLY}


class _ClientScoped(CurrentStateCache):
    """Shared plumbing: the download-cleaner read and client id resolution."""

    def __init__(self, base_url: str, api_key: str, clients: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.clients: dict[str, dict[str, Any]] = clients or {}
        self._session = cleanuparr_session(api_key)

    def _cleaner_clients(self) -> dict[str, dict[str, Any]]:
        """download_cleaner.clients[] by client name."""
        resp = self._session.get(f"{self.base_url}/api/configuration/download_cleaner")
        resp.raise_for_status()
        return {
            c.get("downloadClientName"): c
            for c in (resp.json() or {}).get("clients", [])
        }

    def _client_id(self, name: str) -> str:
        """Resolve a client's id at apply time (it may have been created this run)."""
        resp = self._session.get(f"{self.base_url}/api/configuration/download_client")
        resp.raise_for_status()
        for client in (resp.json() or {}).get("clients", []):
            if client.get("name") == name:
                return str(client["id"])
        raise RuntimeError(f"Cleanuparr download client '{name}' does not exist")

    def _check_supported(self, client: str, setting: str, cfg: dict[str, Any]) -> None:
        client_type = str(cfg.get("type") or "").lower()
        if client_type and setting not in SUPPORTED.get(client_type, frozenset()):
            raise ValueError(
                f"Cleanuparr download client '{client}' ({client_type}) does not "
                f"support '{setting}'"
            )


class CleanuparrClientSettingsProvider(_ClientScoped):
    """``orphaned_files`` / ``unlinked`` / ``dead_torrent`` per download client,
    keyed ``(client, setting)``. UPDATE (or CREATE when unset) — never deleted."""

    def _wanted(self) -> list[tuple[str, str, dict[str, Any]]]:
        out = []
        for client, cfg in self.clients.items():
            for setting in CLIENT_SETTINGS:
                body = (cfg or {}).get(setting)
                if body:
                    self._check_supported(client, setting, cfg or {})
                    out.append((client, setting, body))
        return out

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource["_client"], resource["_setting"])

    def _load_current(self) -> list[dict[str, Any]]:
        wanted = self._wanted()
        if not wanted:
            return []
        by_client = self._cleaner_clients()
        out: list[dict[str, Any]] = []
        for client, setting, _ in wanted:
            field, _path = CLIENT_SETTINGS[setting]
            current = (by_client.get(client) or {}).get(field)
            if current is not None:
                out.append({"_client": client, "_setting": setting, **_strip(current)})
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current = {self.match_key(c): c for c in self.fetch_current()}
        desired = []
        for client, setting, body in self._wanted():
            base = current.get((client, setting))
            merged = (
                merge_over(_strip_meta(base), body)
                if base is not None
                else to_wire(body)
            )
            desired.append({"_client": client, "_setting": setting, **merged})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return flatten(_strip_meta(resource))

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE), f"unexpected op {plan.op!r}"
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op not in (Op.CREATE, Op.UPDATE):
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        client, setting = action.payload["_client"], action.payload["_setting"]
        _field, path = CLIENT_SETTINGS[setting]
        client_id = self._client_id(client)
        resp = self._session.put(
            f"{self.base_url}/api/{path}/{client_id}",
            json=_strip_meta(action.payload),
        )
        resp.raise_for_status()
        self.invalidate_current()


def _strip_meta(obj: dict[str, Any] | None) -> dict[str, Any]:
    return {k: v for k, v in (obj or {}).items() if not k.startswith("_")}


class CleanuparrSeedingRuleProvider(_ClientScoped):
    """Seeding rules per download client, keyed ``(client, rule name)``. CRUD;
    prunable within the clients that declare ``seeding_rules`` (a client without
    the key keeps whatever rules it has)."""

    prunable = True

    def _wanted(self) -> dict[str, dict[str, dict[str, Any]]]:
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for client, cfg in self.clients.items():
            rules = (cfg or {}).get("seeding_rules")
            if rules is None:
                continue
            self._check_supported(client, "seeding_rules", cfg or {})
            out[client] = rules or {}
        return out

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource["_client"], resource.get("name"))

    def _load_current(self) -> list[dict[str, Any]]:
        wanted = self._wanted()
        if not wanted:
            return []
        by_client = self._cleaner_clients()
        out: list[dict[str, Any]] = []
        for client in wanted:
            for rule in (by_client.get(client) or {}).get("seedingRules") or []:
                out.append({"_client": client, **rule})
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        current = {self.match_key(c): c for c in self.fetch_current()}
        desired = []
        for client, rules in self._wanted().items():
            for name, body in rules.items():
                base = current.get((client, name))
                merged = (
                    merge_over({k: v for k, v in base.items() if k != "id"}, body or {})
                    if base is not None
                    else to_wire(body or {})
                )
                desired.append({**merged, "_client": client, "name": name})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        out = flatten(
            {k: v for k, v in resource.items() if k != "id" and not k.startswith("_")}
        )
        # Cleanuparr echoes an unset inactivity limit as null; -1 means the same.
        if out.get("maxInactiveDays") is None:
            out["maxInactiveDays"] = -1
        return {k: coerce_scalar(v) for k, v in out.items()}

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        if plan.op is Op.CREATE:
            return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))
        assert current is not None, f"to_action: {plan.op!r} needs the current rule"
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
        body = _strip_meta(action.payload)
        base = f"{self.base_url}/api/seeding-rules"
        if action.op is Op.CREATE:
            client_id = self._client_id(action.payload["_client"])
            resp = self._session.post(f"{base}/{client_id}", json=body)
        elif action.op is Op.UPDATE:
            rule_id = body.pop("id")
            resp = self._session.put(f"{base}/{rule_id}", json=body)
        elif action.op is Op.DELETE:
            resp = self._session.delete(f"{base}/{body['id']}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
