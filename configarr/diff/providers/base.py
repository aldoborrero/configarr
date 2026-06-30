"""Provider interface: each service/resource implements this."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import requests

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
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
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


class HttpProvider(CurrentStateCache):
    """Base for the *arr providers: an ``X-Api-Key`` session plus HTTP helpers.

    Holds the shared transport boilerplate every Radarr/Sonarr/Prowlarr provider
    repeated: a ``requests.Session`` carrying the API key, ``_url()`` for joining
    paths to ``base_url``, and ``_get/_post/_put/_delete`` wrappers that call
    ``raise_for_status()`` so each call site does not. Subclasses set their own
    ``kind``/``config`` after calling ``super().__init__()``.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str) -> requests.Response:
        resp = self._session.get(self._url(path))
        resp.raise_for_status()
        return resp

    def _post(self, path: str, json: Any) -> requests.Response:
        resp = self._session.post(self._url(path), json=json)
        resp.raise_for_status()
        return resp

    def _put(self, path: str, json: Any) -> requests.Response:
        resp = self._session.put(self._url(path), json=json)
        resp.raise_for_status()
        return resp

    def _delete(self, path: str) -> requests.Response:
        resp = self._session.delete(self._url(path))
        resp.raise_for_status()
        return resp
