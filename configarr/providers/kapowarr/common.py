"""Shared transport for the Kapowarr providers.

Kapowarr (verified against V1.3.2, ``frontend/api.py``) serves its API under
``/api`` and authenticates every route with an ``api_key`` **query parameter**
(``request.values``; there is no header form, and a JSON body cannot carry it),
answering 401 ``ApiKeyInvalid`` without it. Every response is the envelope
``{"error": <name or null>, "result": <payload>}``; errors keep the envelope and
set an HTTP 4xx status.

Because the key travels in the URL, a failed request is reported here with the
path and Kapowarr's error name only — never ``requests``' own message, which
would print the full URL including the key.
"""

from __future__ import annotations

from typing import Any

from configarr.providers.base import CurrentStateCache
from configarr.transport import build_session

# What Kapowarr echoes in place of a stored secret (Constants.CREDENTIAL_REPLACEMENT).
# Sending it back for a setting keeps the stored value.
MASK = "********"


class KapowarrError(RuntimeError):
    """A Kapowarr API call failed (status + Kapowarr's error name, no URL)."""


def norm_base_url(value: Any) -> Any:
    """Kapowarr's ``normalise_base_url``: no trailing slash, ``http://`` added when
    the URL has no scheme. Stored URLs come back in this form."""
    if not isinstance(value, str) or not value:
        return value
    out = value.rstrip("/")
    if not out.startswith(("http://", "https://")):
        out = f"http://{out}"
    return out


class KapowarrProvider(CurrentStateCache):
    """Base for the Kapowarr providers: an ``api_key``-param session plus a
    request helper that unwraps the response envelope."""

    def __init__(self, base_url: str, api_key: str, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self._session = build_session()
        self._session.params = {"api_key": api_key}

    def _call(self, method: str, path: str, json: Any = None) -> Any:
        resp = self._session.request(method, f"{self.base_url}/api{path}", json=json)
        if not resp.ok:
            try:
                error = (resp.json() or {}).get("error")
            except ValueError:
                error = None
            raise KapowarrError(
                f"Kapowarr {method} /api{path} failed: HTTP {resp.status_code}"
                + (f" ({error})" if error else "")
            )
        try:
            body = resp.json()
        except ValueError:
            return None
        return body.get("result") if isinstance(body, dict) else body

    def _get(self, path: str) -> Any:
        return self._call("GET", path)
