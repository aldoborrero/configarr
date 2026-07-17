"""Ownership state: which resources configarr manages, persisted across runs.

configarr matches resources by name and, with ``--prune``, deletes anything on
the server that the config no longer declares. Without a record of what configarr
itself created, that would also delete resources a user made by hand. This module
persists, per (scope, kind), the resources configarr manages — each as a name and
the service id it was created with — so that:

- **prune is ownership-scoped**: only resources configarr created and the config
  has since dropped are deletable; a hand-made resource is never touched; and
- **matching is rename-tolerant**: if a managed resource was renamed on the server
  (its id still exists under a new name), configarr recognizes it by the stored id
  and updates it, instead of creating a confusing duplicate.

The state is a small JSON file (default: ``.configarr-state.json`` next to the
config). A missing or unreadable file is treated as empty state — the safe default
is "configarr owns nothing".
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger("configarr.state")

STATE_VERSION = 2

# scope -> kind -> {managed name: service id (or None if not yet known)}.
_Managed = dict[str, dict[str, dict[str, "int | None"]]]


class State:
    """Managed resources per ``"<service>/<instance>"`` scope and resource kind."""

    def __init__(self, path: Path, managed: _Managed | None = None) -> None:
        self.path = path
        self._managed: _Managed = managed or {}

    @classmethod
    def load(cls, path: Path) -> State:
        """Read state from ``path``; return empty state if absent or unreadable.

        Accepts both the v1 shape (kind -> list of names) and the v2 shape
        (kind -> {name: id}); v1 entries load with unknown ids."""
        if not path.is_file():
            return cls(path)
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("ignoring unreadable state file %s (%s)", path, e)
            return cls(path)
        raw = data.get("managed") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return cls(path)
        managed: _Managed = {}
        for scope, kinds in raw.items():
            if not isinstance(kinds, dict):
                continue
            for kind, entries in kinds.items():
                managed.setdefault(scope, {})[kind] = _coerce_entries(entries)
        return cls(path, managed)

    def managed_keys(self, scope: str, kind: str) -> set[str]:
        """The names configarr is recorded as managing for this scope/kind."""
        return set(self._managed.get(scope, {}).get(kind, {}))

    def managed_id(self, scope: str, kind: str, name: str) -> int | None:
        """The service id recorded for a managed name, or None if unknown."""
        return self._managed.get(scope, {}).get(kind, {}).get(name)

    def managed_ids(self, scope: str, kind: str) -> dict[str, int]:
        """The ``{name: id}`` map for managed names whose service id is known."""
        entry = self._managed.get(scope, {}).get(kind, {})
        return {name: sid for name, sid in entry.items() if isinstance(sid, int)}

    def set_managed(self, scope: str, kind: str, keys: Iterable[Any]) -> None:
        """Replace the managed name set for this scope/kind, preserving the known
        service id of any name that is retained."""
        prior = self._managed.get(scope, {}).get(kind, {})
        entry = {str(k): prior.get(str(k)) for k in keys}
        if entry:
            self._managed.setdefault(scope, {})[kind] = entry
        elif scope in self._managed:
            # Drop empty entries so the file doesn't accumulate dead scopes/kinds.
            self._managed[scope].pop(kind, None)
            if not self._managed[scope]:
                self._managed.pop(scope)

    def set_id(self, scope: str, kind: str, name: str, service_id: int | None) -> None:
        """Record the service id for a managed name (no-op if it isn't managed)."""
        entry = self._managed.get(scope, {}).get(kind)
        if entry is not None and name in entry:
            entry[name] = service_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "managed": {
                scope: {
                    kind: dict(sorted(entry.items()))
                    for kind, entry in sorted(kinds.items())
                }
                for scope, kinds in sorted(self._managed.items())
            },
        }

    def save(self) -> None:
        """Write the state atomically (temp file + replace)."""
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        tmp.replace(self.path)


def _coerce_entries(entries: Any) -> dict[str, int | None]:
    """Normalize one kind's stored entry to ``{name: id|None}`` from either shape."""
    if isinstance(entries, list):  # v1: a list of names, ids unknown
        return {str(name): None for name in entries}
    if isinstance(entries, dict):  # v2: {name: id}
        out: dict[str, int | None] = {}
        for name, sid in entries.items():
            out[str(name)] = sid if isinstance(sid, int) else None
        return out
    return {}
