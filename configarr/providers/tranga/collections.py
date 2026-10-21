"""Tranga collections: file libraries, library connectors, notification connectors.

All three are prunable (each has a ``DELETE``), and Tranga creates with ``PUT``:

- **File libraries** (``/v2/FileLibrary``) — name-keyed; ``PATCH /{key}`` renames or
  moves one in place. Deleting a library un-assigns its manga (Tranga sets their
  library to null), so prune with care.
- **Library connectors** (``/v2/LibraryConnector``) — Kavita/Komga servers Tranga
  asks to rescan after downloads. Keyed by ``(type, base_url)``; the API key is
  never returned and there is no update endpoint, so an existing connector is only
  ever created or deleted. Tranga tests the credentials on create and answers 401
  when they are wrong.
- **Notification connectors** (``/v2/NotificationConnector``) — name-keyed, stored
  as a generic webhook (url, method, body, headers). There is no update endpoint, so
  an update deletes and recreates the connector under the same name. ``type:
  gotify`` is expanded locally the same way Tranga's own Gotify endpoint does, so a
  connector made in the UI diffs clean against the same config.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from configarr.normalize import coerce_scalar, fingerprint_secret
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.tranga.common import TrangaClient

log = logging.getLogger(__name__)


def _warn_unknown(
    noun: str, name: Any, settings: dict[str, Any], known: set[str]
) -> None:
    unknown = sorted(k for k in settings if k not in known)
    if unknown:
        log.warning(
            "Tranga %s '%s': ignoring unknown setting(s): %s",
            noun,
            name,
            ", ".join(unknown),
        )


class _TrangaCollection(TrangaClient, CurrentStateCache):
    """Shared to_action for the Tranga collections: CREATE carries desired, UPDATE
    desired plus the current server key, DELETE the current object."""

    prunable = True

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        if plan.op is Op.CREATE:
            return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))
        assert current is not None, f"to_action: {plan.op!r} needs the current object"
        if plan.op is Op.DELETE:
            return Action(op=plan.op, key=plan.key, payload=dict(current))
        if plan.op is Op.UPDATE:
            return Action(
                op=plan.op,
                key=plan.key,
                payload={**(desired or {}), "_current": dict(current)},
            )
        raise AssertionError(f"to_action: unexpected op {plan.op!r}")


# -- file libraries -------------------------------------------------------------


class TrangaFileLibraryProvider(_TrangaCollection):
    """File libraries, keyed by name: ``{name: {base_path}}``."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config: dict[str, dict[str, Any]] = config or {}

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("libraryName")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        libraries: list[dict[str, Any]] = self._request("GET", "/v2/FileLibrary").json()
        return libraries or []

    def build_desired(self) -> list[dict[str, Any]]:
        current = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, settings in self.config.items():
            settings = settings or {}
            _warn_unknown("file library", name, settings, {"base_path"})
            base_path = settings.get("base_path")
            if base_path in (None, ""):
                if name not in current:
                    raise ValueError(
                        f"Tranga file library '{name}' is missing required 'base_path'"
                    )
                base_path = current[name].get("basePath")
            desired.append({"libraryName": name, "basePath": base_path})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return {"basePath": resource.get("basePath")}

    def apply(self, action: Action) -> None:
        p = action.payload
        if action.op is Op.CREATE:
            self._request(
                "PUT",
                "/v2/FileLibrary",
                json={"basePath": p["basePath"], "libraryName": p["libraryName"]},
                create=True,
            )
        elif action.op is Op.UPDATE:
            key = p["_current"]["key"]
            self._request(
                "PATCH",
                f"/v2/FileLibrary/{quote(key, safe='')}",
                json={"path": p["basePath"], "name": p["libraryName"]},
            )
        elif action.op is Op.DELETE:
            self._request("DELETE", f"/v2/FileLibrary/{quote(p['key'], safe='')}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()


# -- library connectors ---------------------------------------------------------

# Tranga's LibraryType values, by their lowercase config spelling.
LIBRARY_TYPES: dict[str, str] = {"kavita": "Kavita", "komga": "Komga"}


def _canonical_type(value: Any) -> str:
    canonical = LIBRARY_TYPES.get(str(value).lower())
    if canonical is None:
        raise ValueError(
            f"Tranga: unknown library connector type '{value}' "
            f"(expected one of {', '.join(LIBRARY_TYPES)})"
        )
    return canonical


def _strip_url(url: Any) -> str:
    # Tranga stores BaseUrl with trailing '/' and ' ' trimmed.
    return str(url or "").rstrip("/ ")


class TrangaLibraryConnectorProvider(_TrangaCollection):
    """Kavita/Komga connectors: a list of ``{type, base_url, api_key}``, keyed by
    ``(type, base_url)``. Create-or-delete only (nothing comparable to update)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config: list[dict[str, Any]] = config or []

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource.get("type"), resource.get("baseUrl"))

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        connectors: list[dict[str, Any]] = self._request(
            "GET", "/v2/LibraryConnector"
        ).json()
        return connectors or []

    def build_desired(self) -> list[dict[str, Any]]:
        current = {self.match_key(c) for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for entry in self.config:
            entry = entry or {}
            for required in ("type", "base_url"):
                if not entry.get(required):
                    raise ValueError(
                        f"Tranga library connector {entry!r} is missing "
                        f"required '{required}'"
                    )
            _warn_unknown(
                "library connector",
                entry["base_url"],
                entry,
                {"type", "base_url", "api_key"},
            )
            obj = {
                "type": _canonical_type(entry["type"]),
                "baseUrl": _strip_url(entry["base_url"]),
            }
            if self.match_key(obj) not in current and not entry.get("api_key"):
                raise ValueError(
                    f"Tranga {obj['type']} connector '{obj['baseUrl']}' is missing "
                    "required 'api_key'"
                )
            desired.append({**obj, "_apiKey": entry.get("api_key")})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return {"type": resource.get("type"), "baseUrl": resource.get("baseUrl")}

    def apply(self, action: Action) -> None:
        p = action.payload
        if action.op is Op.CREATE:
            self._request(
                "PUT",
                f"/v2/LibraryConnector/{p['type']}",
                json={"url": p["baseUrl"], "apiKey": p["_apiKey"]},
                create=True,
            )
        elif action.op is Op.DELETE:
            self._request("DELETE", f"/v2/LibraryConnector/{quote(p['key'], safe='')}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()


# -- notification connectors ----------------------------------------------------

NOTIFICATION_TYPES = ("generic", "gotify")
_GENERIC_KEYS = {"type", "url", "http_method", "body", "headers"}
_GOTIFY_KEYS = {"type", "url", "app_token", "priority"}


def _gotify(name: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Expand a Gotify connector exactly as Tranga's ``PUT
    /v2/NotificationConnector/Gotify`` does before storing it."""
    for required in ("url", "app_token"):
        if not settings.get(required):
            raise ValueError(
                f"Tranga gotify connector '{name}' is missing required '{required}'"
            )
    parts = urlsplit(str(settings["url"]))
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"Tranga gotify connector '{name}': url must be http(s)")
    url = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path.rstrip("/") + "/message",
            parts.query,
            parts.fragment,
        )
    )
    priority = int(settings.get("priority", 5))
    return {
        "name": name,
        "url": url,
        "httpMethod": "POST",
        "body": f'{{"message": "%text", "title": "%title", "Priority": {priority}}}',
        "headers": {"X-Gotify-Key": str(settings["app_token"])},
    }


class TrangaNotificationConnectorProvider(_TrangaCollection):
    """Notification connectors, keyed by name: ``{name: {url, http_method, body,
    headers}}`` or ``{name: {type: gotify, url, app_token, priority}}``."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config: dict[str, dict[str, Any]] = config or {}

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        connectors: list[dict[str, Any]] = self._request(
            "GET", "/v2/NotificationConnector"
        ).json()
        return connectors or []

    def build_desired(self) -> list[dict[str, Any]]:
        desired: list[dict[str, Any]] = []
        for name, settings in self.config.items():
            settings = settings or {}
            kind = str(settings.get("type", "generic")).lower()
            if kind not in NOTIFICATION_TYPES:
                raise ValueError(
                    f"Tranga notification connector '{name}': unknown type "
                    f"'{settings.get('type')}' (expected one of "
                    f"{', '.join(NOTIFICATION_TYPES)})"
                )
            if kind == "gotify":
                _warn_unknown("notification connector", name, settings, _GOTIFY_KEYS)
                desired.append(_gotify(name, settings))
                continue
            _warn_unknown("notification connector", name, settings, _GENERIC_KEYS)
            for required in ("url", "body"):
                if not settings.get(required):
                    raise ValueError(
                        f"Tranga notification connector '{name}' is missing "
                        f"required '{required}'"
                    )
            desired.append(
                {
                    "name": name,
                    "url": settings["url"],
                    "httpMethod": str(settings.get("http_method", "POST")).upper(),
                    "body": settings["body"],
                    "headers": {
                        str(k): str(v)
                        for k, v in (settings.get("headers") or {}).items()
                    },
                }
            )
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        # Headers usually carry the credential (X-Gotify-Key, Authorization), and
        # Tranga returns them in clear: fingerprint every value so a change still
        # diffs but the secret never enters the plan.
        headers = resource.get("headers") or {}
        return {
            "url": resource.get("url"),
            "httpMethod": str(resource.get("httpMethod") or "").upper(),
            "body": coerce_scalar(resource.get("body")),
            "headers": {k: fingerprint_secret(v) for k, v in sorted(headers.items())},
        }

    def _create(self, p: dict[str, Any]) -> None:
        self._request(
            "PUT",
            "/v2/NotificationConnector",
            json={k: p[k] for k in ("name", "url", "httpMethod", "body", "headers")},
            create=True,
        )

    def _delete(self, name: str) -> None:
        self._request("DELETE", f"/v2/NotificationConnector/{quote(name, safe='')}")

    def apply(self, action: Action) -> None:
        p = action.payload
        if action.op is Op.CREATE:
            self._create(p)
        elif action.op is Op.UPDATE:
            # No update endpoint: replace under the same name.
            self._delete(p["name"])
            self._create(p)
        elif action.op is Op.DELETE:
            self._delete(p["name"])
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
