"""Resolve a TRaSH-Guides checkout to its root directory.

Only ``source: local`` is supported today (per the design decision to start
offline-first); a runtime ``git`` fetch is a later phase. Relative ``path`` values
resolve against the config file's directory, matching how recyclarr resolves a
``LocalProviderLocation`` relative to its config.
"""

from __future__ import annotations

from pathlib import Path

from configarr.models import TrashConfig
from configarr.trash.errors import TrashError


def resolve_source(trash: TrashConfig, base_dir: Path) -> Path:
    """Return the guide root directory for a ``trash:`` block."""
    if trash.source != "local":
        raise TrashError(
            f"unsupported trash source {trash.source!r}; only 'local' is supported"
        )
    if not trash.path:
        raise TrashError("trash source 'local' requires a 'path' to a Guides checkout")

    root = Path(trash.path).expanduser()
    if not root.is_absolute():
        root = base_dir / root
    if not root.is_dir():
        raise TrashError(f"TRaSH guide path not found: {root}")
    return root
