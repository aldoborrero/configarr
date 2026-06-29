"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

from typing import Any

MASK = "********"  # Radarr/Sonarr return ApiKey/Password fields masked

# Provider-Field secrets are never echoed in clear text, so a configured value can
# never be compared against the masked server value. Skip them from the diff by name
# on both sides; apply still POSTs/PUTs the real value from build_desired.
SECRET_FIELD_NAMES = frozenset({"apiKey", "password", "passKey"})


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
        if low in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity", "nan"}:
            return value
        try:
            return float(value)
        except ValueError:
            pass
    return value


def drop_masked_secrets(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove fields whose value is the secret mask; their real value is unknown."""
    return {k: v for k, v in fields.items() if v != MASK}


def drop_secret_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Remove known secret-name fields so a configured secret never diffs against the
    masked server value (provider-Field resources). Also drops mask-valued fields."""
    return {
        k: v for k, v in fields.items() if k not in SECRET_FIELD_NAMES and v != MASK
    }
