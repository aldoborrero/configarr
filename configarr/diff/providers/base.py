"""Provider interface: each service/resource implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Protocol, runtime_checkable

from configarr.diff.model import Op, ResourcePlan


@dataclass
class Action:
    op: Op
    key: Hashable
    payload: dict[str, Any]  # full object to POST/PUT


@runtime_checkable
class ResourceProvider(Protocol):
    kind: str
    # Providers that expose a per-resource DELETE endpoint set this True so the
    # engine may prune unmanaged resources under --prune. Singletons and
    # set-only/config providers (naming, sabnzbd.*, bazarr settings sections)
    # leave it False, since deletion is meaningless or unsafe for them.
    prunable: bool = False

    def match_key(self, resource: dict[str, Any]) -> Hashable: ...
    def fetch_current(self) -> list[dict[str, Any]]: ...
    def build_desired(self) -> list[dict[str, Any]]: ...
    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]: ...
    def to_action(
        self, plan: ResourcePlan, current: dict | None, desired: dict | None
    ) -> Action: ...
    def apply(self, action: Action) -> None: ...


class CurrentStateCache:
    """Mixin memoizing the current-state fetch per provider instance.

    A plan reads current state twice — the runner diffs against it, and most
    providers also read it inside ``build_desired()`` to merge over current.
    Without memoization that is two GETs per plan (up to four through the
    apply-then-replan harness), and the two reads can observe different server
    state (TOCTOU). Providers implement ``_load_current()`` for the raw HTTP
    read; ``fetch_current()`` caches it. ``apply()`` MUST call
    ``invalidate_current()`` after a successful write so a re-plan observes
    post-write state.
    """

    _current_cache: list[dict[str, Any]] | None = None
    # Additive by default; providers that expose a DELETE endpoint set this True
    # to participate in --prune (see ResourceProvider.prunable).
    prunable: bool = False

    def fetch_current(self) -> list[dict[str, Any]]:
        if self._current_cache is None:
            self._current_cache = self._load_current()
        return self._current_cache

    def invalidate_current(self) -> None:
        self._current_cache = None

    def _load_current(self) -> list[dict[str, Any]]:
        raise NotImplementedError
