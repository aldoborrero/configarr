"""Ownership state: which resources configarr manages, persisted across runs.

configarr matches resources by name and, with ``--prune``, deletes anything on
the server that the config no longer declares. Without a record of what configarr
itself created, that would also delete resources a user made by hand. This module
persists the set of keys configarr manages per (scope, kind) so prune can be
**ownership-scoped**: it deletes only resources configarr previously created that
the config has since dropped, and never touches anything configarr didn't make.

The state is a small JSON file (default: ``.configarr-state.json`` next to the
config). It is read before a run and rewritten after a successful apply. A missing
or unreadable file is treated as empty state — the safe default is "configarr owns
nothing", so prune deletes nothing until configarr has recorded what it manages.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Hashable, Iterable
from pathlib import Path
from typing import Any

log = logging.getLogger("configarr.state")

STATE_VERSION = 1


class State:
    """Managed keys per ``"<service>/<instance>"`` scope and resource kind."""

    def __init__(
        self, path: Path, managed: dict[str, dict[str, list[str]]] | None = None
    ) -> None:
        self.path = path
        # scope -> kind -> sorted list of managed keys.
        self._managed: dict[str, dict[str, set[str]]] = {
            scope: {kind: set(keys) for kind, keys in kinds.items()}
            for scope, kinds in (managed or {}).items()
        }

    @classmethod
    def load(cls, path: Path) -> State:
        """Read state from ``path``; return empty state if absent or unreadable."""
        if not path.is_file():
            return cls(path)
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("ignoring unreadable state file %s (%s)", path, e)
            return cls(path)
        managed = data.get("managed") if isinstance(data, dict) else None
        if not isinstance(managed, dict):
            return cls(path)
        return cls(path, managed)

    def managed_keys(self, scope: str, kind: str) -> set[str]:
        """The keys configarr is recorded as managing for this scope/kind."""
        return set(self._managed.get(scope, {}).get(kind, set()))

    def set_managed(self, scope: str, kind: str, keys: Iterable[Hashable]) -> None:
        """Replace the managed key set for this scope/kind (keys stored as strings)."""
        key_set = {str(k) for k in keys}
        if key_set:
            self._managed.setdefault(scope, {})[kind] = key_set
        elif scope in self._managed:
            # Drop empty entries so the file doesn't accumulate dead scopes/kinds.
            self._managed[scope].pop(kind, None)
            if not self._managed[scope]:
                self._managed.pop(scope)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "managed": {
                scope: {kind: sorted(keys) for kind, keys in kinds.items()}
                for scope, kinds in sorted(self._managed.items())
            },
        }

    def save(self) -> None:
        """Write the state atomically (temp file + replace)."""
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2) + "\n")
        tmp.replace(self.path)
