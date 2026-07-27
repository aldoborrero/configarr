"""Canonicalization helpers to avoid false diffs (see diffing-engine-radarr-notes)."""

from __future__ import annotations

import hashlib
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


# Field-name policy for secrets a provider echoes in CLEAR TEXT (Bazarr), where there
# is no schema privacy metadata to key off. Matching is by the leaf name, case- and
# underscore-insensitive. This is used both to fingerprint such values before they
# enter a plan (redact_secret_fields) and as render's output-layer backstop. It is a
# heuristic: a secret under a name none of these substrings match is not recognized.
_SECRET_NAME_HINTS = (
    "password",
    "passwd",
    "passkey",
    "passphrase",
    "apikey",
    "userkey",  # Pushover userKey — secret despite lacking "password"/"apikey"
    "token",
    "secret",
    "credential",
    "cookie",
)


def is_secret_name(name: str) -> bool:
    """True if a field name looks like it holds a secret. Compares the leaf segment
    (after the last ``.``) with separators removed and case folded."""
    leaf = str(name).rsplit(".", 1)[-1].replace("_", "").lower()
    return any(hint in leaf for hint in _SECRET_NAME_HINTS)


def fingerprint_secret(value: Any) -> str:
    """A stable, non-reversible stand-in for a secret value. Equal secrets share a
    fingerprint (an unchanged config does not diff) and a changed secret changes it
    (the update is still detected), while the cleartext never enters the plan."""
    if value is None or value == "":
        return "secret:unset"
    return "secret:" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


def redact_secret_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Replace secret-named field values with a fingerprint. For providers whose API
    returns secrets in clear text (Bazarr): the diff still compares and detects a
    changed secret, but the raw value never enters the plan. Apply is unaffected — it
    writes the real value from the desired config, not from this normalized view."""
    return {
        k: (fingerprint_secret(v) if is_secret_name(k) else v)
        for k, v in fields.items()
    }
