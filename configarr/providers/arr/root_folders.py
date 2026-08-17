"""Root-folder provider (Radarr/Sonarr share the API). Client-free: talks HTTP
via requests.

Root folders are create-only: the API exposes ``POST /rootfolder`` and
``DELETE /rootfolder/{id}`` but no update. The config lists
``settings.root_folders`` as ``[{path: ...}]``. build_desired emits one ``{path}``
per listed folder; because the match key *is* the path, an existing folder always
reports UNCHANGED and an absent one CREATE — there is no UPDATE path (rollout
work-list #4). Not a full-replace resource: nothing is merged over current.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, HttpProvider


def _norm_path(path: str | None) -> str | None:
    """Normalize a root-folder path for matching: the *arr API stores paths without a
    trailing slash, so ``/data/media/`` and ``/data/media`` are the same folder (a
    bare ``/`` is preserved)."""
    if path is None:
        return path
    return path.rstrip("/") or "/"


class RootFolderProvider(HttpProvider):
    """Diffs Radarr/Sonarr root folders by filesystem path; create-only (no update)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config = config or []

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _norm_path(resource.get("path"))

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/rootfolder").json()
        return data

    def build_desired(self) -> list[dict[str, Any]]:
        return [
            {"path": _norm_path(entry["path"])}
            for entry in self.config
            if entry.get("path")
        ]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Path is the only managed field; server-side stats (accessible/freeSpace)
        # are read-only and never compared. Trailing slashes are stripped so a config
        # path matches the server-normalized one.
        return {"path": _norm_path(resource.get("path"))}

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.CREATE, f"to_action: unexpected op {plan.op!r}"
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op is not Op.CREATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self._post("/api/v3/rootfolder", json=action.payload)
        self.invalidate_current()
