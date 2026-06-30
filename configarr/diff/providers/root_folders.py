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

import requests

from configarr.diff.model import Op, ResourcePlan
from configarr.diff.providers.base import Action, CurrentStateCache


class RootFolderProvider(CurrentStateCache):
    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or []
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("path")

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/rootfolder"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    def build_desired(self) -> list[dict[str, Any]]:
        return [{"path": entry["path"]} for entry in self.config if entry.get("path")]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Path is the only managed field; server-side stats (accessible/freeSpace)
        # are read-only and never compared.
        return {"path": resource.get("path")}

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
        resp = self._session.post(self._url("/api/v3/rootfolder"), json=action.payload)
        resp.raise_for_status()
        self.invalidate_current()
