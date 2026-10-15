"""Shared helpers for the Cleanuparr providers.

Cleanuparr's API speaks camelCase JSON (``failedImport.maxStrikes``) and reads it
case-insensitively, while configarr configs are snake_case (``failed_import:
max_strikes:``). Rather than a fixed rename table, a config key is matched against
the server's own keys by a loose form (lowercase, underscores dropped), so
``rolling_size_mb`` lands on the server's ``rollingSizeMB``; a key the server does
not return yet falls back to plain camelCase.

Every config section is a full-replace ``PUT`` (an omitted field is reset to its
default), so section providers always merge the configured keys over the current
object and write the whole result back.

Secrets (``apiKey``, ``password``) come back masked as ``SECRET_PLACEHOLDER``; a
``PUT`` carrying the placeholder keeps the stored value.
"""

from __future__ import annotations

from typing import Any

import requests

from configarr.normalize import coerce_scalar
from configarr.transport import build_session

# What Cleanuparr's SensitiveDataResolver serializes a secret string as.
SECRET_PLACEHOLDER = "••••••••"


def cleanuparr_session(api_key: str) -> requests.Session:
    """A session authenticated the way Cleanuparr's ApiKey scheme expects."""
    session = build_session()
    session.headers["X-Api-Key"] = api_key
    return session


def loose(key: str) -> str:
    """The comparison form of a key: lowercase, no underscores."""
    return key.replace("_", "").lower()


def camelize(key: str) -> str:
    """snake_case -> camelCase (a key already in camelCase passes through)."""
    head, *rest = key.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _key_for(config_key: str, current: dict[str, Any]) -> str:
    """The server's spelling of ``config_key`` when it has one, else camelCase."""
    wanted = loose(config_key)
    for server_key in current:
        if loose(server_key) == wanted:
            return server_key
    return camelize(config_key)


def merge_over(current: Any, config: Any) -> Any:
    """Merge a snake_case config tree over a camelCase server object.

    Dicts merge key by key (config keys mapped onto the server's spelling); any
    other value replaces the current one. A string that only differs from the
    current value in case keeps the server's spelling, so an enum written as
    ``exclude`` does not diff against Cleanuparr's ``Exclude``.
    """
    if isinstance(config, dict):
        base = dict(current) if isinstance(current, dict) else {}
        for key, value in config.items():
            server_key = _key_for(key, base)
            base[server_key] = merge_over(base.get(server_key), value)
        return base
    if (
        isinstance(config, str)
        and isinstance(current, str)
        and config.lower() == current.lower()
    ):
        return current
    return config


def to_wire(config: Any) -> Any:
    """camelCase a config tree that has no server object to merge over (a new
    resource)."""
    if isinstance(config, dict):
        return {camelize(k): to_wire(v) for k, v in config.items()}
    if isinstance(config, list):
        return [to_wire(v) for v in config]
    return config


def flatten(obj: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts to dotted paths so a plan shows
    ``failedImport.maxStrikes: 0 -> 3`` instead of the whole sub-object. Lists stay
    whole values; scalars are coerced so ``"3"`` and ``3`` compare equal."""
    out: dict[str, Any] = {}
    for key, value in obj.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{path}."))
        else:
            out[path] = coerce_scalar(value)
    return out
