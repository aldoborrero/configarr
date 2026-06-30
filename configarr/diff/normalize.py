"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

from typing import Any, Collection, Iterable

MASK = "********"  # Radarr/Sonarr return ApiKey/Password fields masked

# Provider-Field secrets are never echoed in clear text, so a configured value can
# never be compared against the masked server value. Which fields are secret comes
# from the schema's per-field privacy metadata (FieldDefinitionAttribute), NOT a name
# list — a Telegram botToken or Pushover userKey is secret without an apiKey/password
# name. The *arr server copies each field's privacy onto the resource it returns, so
# reading privacy off a schema-default field or a current field is schema-derived.
SECRET_PRIVACY = frozenset({"apiKey", "password"})


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


def secret_field_names(fields: Iterable[dict[str, Any]]) -> set[str]:
    """Names of provider-Field entries whose schema privacy marks them secret."""
    return {f["name"] for f in fields if f.get("privacy") in SECRET_PRIVACY}


def drop_secret_fields(
    fields: dict[str, Any], secret_names: Collection[str]
) -> dict[str, Any]:
    """Remove privacy-secret fields so a configured secret never diffs against the
    masked server value (provider-Field resources). Also drops mask-valued fields."""
    return {k: v for k, v in fields.items() if k not in secret_names and v != MASK}
