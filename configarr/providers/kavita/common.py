"""Shared helpers for the Kavita providers.

Kavita has no static API-key header. An *auth key* (Kavita's user API key) is
exchanged for a JWT with ``POST /api/plugin/authenticate?apiKey=…&pluginName=…``
and the token is then sent as ``Authorization: Bearer <token>``. ``KavitaAuth`` does
that exchange lazily, on the first request a provider makes, and reuses the token
for every later call through the same session.

Kavita serializes its enums as integers. Config values are written by name (``book``,
``light_novel``, ``webp``) and mapped here; an integer passes through unchanged.
"""

from __future__ import annotations

from typing import Any

import requests

from configarr.transport import build_session

PLUGIN_NAME = "configarr"


class KavitaAuth(requests.auth.AuthBase):
    """Bearer auth from a Kavita auth key, exchanged for a JWT on first use."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._token: str | None = None

    def token(self) -> str:
        if self._token is None:
            if not self.api_key:
                raise ValueError("Kavita: 'api_key' (an auth key) is required")
            resp = build_session().post(
                f"{self.base_url}/api/plugin/authenticate",
                params={"apiKey": self.api_key, "pluginName": PLUGIN_NAME},
            )
            if resp.status_code == 401:
                raise ValueError(
                    "Kavita rejected the auth key — check 'api_key' (Kavita's "
                    "user auth key, not a device/OPDS key)"
                )
            resp.raise_for_status()
            token = (resp.json() or {}).get("token")
            if not token:
                raise ValueError("Kavita: /api/plugin/authenticate returned no token")
            self._token = str(token)
        return self._token

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self.token()}"
        return r


def kavita_session(base_url: str, api_key: str) -> requests.Session:
    """A retrying session that authenticates the way Kavita expects."""
    session = build_session()
    session.auth = KavitaAuth(base_url, api_key)
    return session


def _loose(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def enum_value(enum: dict[str, int], value: Any, what: str) -> int:
    """Map a config enum value (name in any case/spacing, or the raw int) to Kavita's
    integer."""
    if isinstance(value, bool):
        raise ValueError(f"Kavita: invalid {what} {value!r}")
    if isinstance(value, int):
        if value not in enum.values():
            raise ValueError(f"Kavita: unknown {what} {value!r}")
        return value
    wanted = _loose(str(value))
    found = next((n for name, n in enum.items() if _loose(name) == wanted), None)
    if found is None:
        raise ValueError(
            f"Kavita: unknown {what} {value!r} (expected one of {', '.join(enum)})"
        )
    return found


def enum_name(enum: dict[str, int], value: Any) -> Any:
    """Kavita's integer back to its config name, for readable plans. Unknown values
    pass through unchanged."""
    for name, number in enum.items():
        if number == value and not isinstance(value, bool):
            return name
    return value


# Matched loosely (case, ``_``/``-``/spaces ignored): ``light_novel`` == ``LightNovel``.
LIBRARY_TYPES: dict[str, int] = {
    "manga": 0,
    "comic": 1,
    "book": 2,
    "image": 3,
    "light_novel": 4,
    "comic_vine": 5,
}
FILE_TYPE_GROUPS: dict[str, int] = {
    "archive": 1,
    "epub": 2,
    "pdf": 3,
    "images": 4,
}
METADATA_PROVIDERS: dict[str, int] = {
    "hardcover": 2,
    "mangabaka": 3,
    "comic_book_roundup": 4,
}
ENCODE_FORMATS: dict[str, int] = {"png": 0, "webp": 1, "avif": 2}
COVER_IMAGE_SIZES: dict[str, int] = {"default": 1, "medium": 2, "large": 3, "xlarge": 4}
PDF_RENDER_RESOLUTIONS: dict[str, int] = {"default": 1, "high": 2, "ultra": 3}
AGE_RATINGS: dict[str, int] = {
    "not_applicable": -1,
    "unknown": 0,
    "rating_pending": 1,
    "early_childhood": 2,
    "everyone": 3,
    "g": 4,
    "everyone_10_plus": 5,
    "pg": 6,
    "kids_to_adults": 7,
    "teen": 8,
    "mature_15_plus": 9,
    "mature_17_plus": 10,
    "mature": 11,
    "r18_plus": 12,
    "adults_only": 13,
    "x18_plus": 14,
}
