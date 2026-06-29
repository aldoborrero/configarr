"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

from typing import Any

MASK = "********"  # Radarr/Sonarr return ApiKey/Password fields masked


def coerce_scalar(value: Any) -> Any:
    """Coerce numeric/bool strings so '5' == 5 and 'true' == True."""
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "false"}:
            return low == "true"
        try:
            return int(value)
        except ValueError:
            pass
        # Guard so free-text fields don't coerce to inf/nan via float().
        if low in {"inf", "+inf", "-inf", "infinity", "nan"}:
            return value
        try:
            return float(value)
        except ValueError:
            pass
    return value


def drop_masked_secrets(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove fields whose value is the secret mask; their real value is unknown."""
    return {k: v for k, v in fields.items() if v != MASK}
