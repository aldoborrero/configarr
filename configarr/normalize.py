"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from typing import Any

MASK = "********"  # Radarr/Sonarr return ApiKey/Password fields masked

# Only "clean" numeric strings coerce, so string identity is preserved for values that
# happen to look numeric: zero-padded ids ("007"), underscore-grouped ("1_000"), and
# exponent forms ("1e3") stay strings. Python's int()/float() would otherwise silently
# rewrite them, masking a real string-vs-number drift.
_INT_RE = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
_FLOAT_RE = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)")

# Provider-Field secrets are never echoed in clear text, so a configured value can
# never be compared against the masked server value. Which fields are secret comes
# from the schema's per-field privacy metadata (FieldDefinitionAttribute), NOT a name
# list — a Telegram botToken or Pushover userKey is secret without an apiKey/password
# name. The *arr server copies each field's privacy onto the resource it returns, so
# reading privacy off a schema-default field or a current field is schema-derived.
SECRET_PRIVACY = frozenset({"apiKey", "password"})


def coerce_scalar(value: Any) -> Any:
    """Coerce clean numeric/bool strings so '5' == 5 and 'true' == True. Values that
    only look numeric (leading zeros, underscores, exponents, inf/nan) are left as-is
    so their string identity is preserved."""
    if isinstance(value, str):
        s = value.strip()
        low = s.lower()
        if low in {"true", "false"}:
            return low == "true"
        if _INT_RE.fullmatch(s):
            return int(s)
        if _FLOAT_RE.fullmatch(s):
            return float(s)
    return value


def secret_field_names(fields: Iterable[dict[str, Any]]) -> set[str]:
    """Names of provider-Field entries whose schema privacy marks them secret."""
    return {f["name"] for f in fields if f.get("privacy") in SECRET_PRIVACY}


def drop_secret_fields(
    fields: dict[str, Any], secret_names: Collection[str] = ()
) -> dict[str, Any]:
    """Remove fields that can't be compared against the server's response: those whose
    name is a known schema-privacy secret (the server echoes them masked) and those
    whose value is literally the mask. Pass ``secret_names`` for provider-Field
    resources; omit it when only mask-valued fields must be dropped."""
    return {k: v for k, v in fields.items() if k not in secret_names and v != MASK}
