"""Shared helpers for the Tranga providers.

Tranga v2's API (``/v2/...``) has no authentication of its own, so ``api_key`` is
optional; when one is configured it is sent as ``X-Api-Key`` (for an auth proxy in
front of Tranga), otherwise no credential is sent.

Tranga creates resources with ``PUT`` — which is *not* idempotent there (a retried
create adds a second library). Creates therefore go through a session with retries
disabled; reads, PATCHes and DELETEs use the normal retrying session.
"""

from __future__ import annotations

import requests

from configarr.transport import build_session


def tranga_session(api_key: str, retries: int | None = None) -> requests.Session:
    """A session for Tranga, carrying ``X-Api-Key`` only when one is configured."""
    session = build_session(retries=retries)
    if api_key:
        session.headers["X-Api-Key"] = api_key
    return session


class TrangaClient:
    """``base_url`` + the two sessions every Tranga provider needs."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = tranga_session(api_key)
        self._create_session = tranga_session(api_key, retries=0)

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self, method: str, path: str, *, json: object = None, create: bool = False
    ) -> requests.Response:
        session = self._create_session if create else self._session
        resp = session.request(method, self._url(path), json=json)
        resp.raise_for_status()
        return resp
