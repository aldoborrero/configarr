"""Kavita server settings (``GET``/``POST /api/settings``). Client-free.

The settings object is one ``ServerSettingDto``, read with ``GET /api/settings`` and
written with ``POST /api/settings`` of the **whole** DTO: Kavita walks every stored
setting and overwrites it from the posted object, so an omitted field would be
reset. This is therefore an over-current singleton — the configured keys are merged
over the current DTO (snake_case config keys loosely matched onto Kavita's camelCase
fields) and the whole result is posted back. Plans diff dotted paths
(``oidcConfig.providerName``).

Secrets:

- ``oidcConfig.secret`` comes back masked as ``"*" * len(secret)``, and Kavita keeps
  the stored secret when it receives exactly that mask. So an unconfigured secret is
  sent back masked (unchanged), a configured one is sent as is, and the diff can only
  compare **lengths**: a rotated secret of the same length does not show in a plan.
- ``smtpConfig.password`` comes back in clear text, so it is compared by fingerprint
  and never enters a plan in the clear.

Kavita builds its OIDC handler once at startup, so a change to the authority, client
id, secret or custom scopes is only picked up after a restart (and a new authority
also unlinks every user's OIDC login). configarr warns about it; it never restarts
anything.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any

from configarr.normalize import fingerprint_secret
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.cleanuparr.common import flatten, loose, merge_over
from configarr.providers.kavita.common import (
    AGE_RATINGS,
    COVER_IMAGE_SIZES,
    ENCODE_FORMATS,
    PDF_RENDER_RESOLUTIONS,
    enum_name,
    enum_value,
    kavita_session,
)

log = logging.getLogger(__name__)

_SINGLETON = "settings"

# Short config aliases for the two nested objects.
_ALIASES = {"oidc": "oidc_config", "smtp": "smtp_config"}

# Fields Kavita reports but never takes from a POST (install identity, stats, the
# cache directory) plus the OIDC ``enabled`` flag, which Kavita derives from
# ``authority``. Kept out of the diff; configuring one only earns a warning.
READ_ONLY_PATHS = frozenset(
    {
        "cacheDirectory",
        "installVersion",
        "installId",
        "firstInstallDate",
        "firstInstallVersion",
        "statsApiHits",
        "oidcConfig.enabled",
    }
)
_READ_ONLY_LOOSE = {loose(p.split(".")[-1]) for p in READ_ONLY_PATHS if "." not in p}

# Top-level / OIDC enum fields: dotted API path -> (enum, label).
_ENUMS: dict[str, tuple[dict[str, int], str]] = {
    "encodeMediaAs": (ENCODE_FORMATS, "encode_media_as"),
    "coverImageSize": (COVER_IMAGE_SIZES, "cover_image_size"),
    "pdfRenderResolution": (PDF_RENDER_RESOLUTIONS, "pdf_render_resolution"),
    "oidcConfig.defaultAgeRestriction": (AGE_RATINGS, "oidc.default_age_restriction"),
}

# OIDC fields Kavita only reads at startup.
RESTART_PATHS = (
    "oidcConfig.authority",
    "oidcConfig.clientId",
    "oidcConfig.secret",
    "oidcConfig.customScopes",
)
_OIDC_SECRET = "oidcConfig.secret"
_SMTP_PASSWORD = "smtpConfig.password"


def _secret_length_marker(value: Any) -> str:
    """Comparable stand-in for the OIDC secret: Kavita only reveals its length."""
    return fingerprint_secret("*" * len(str(value or "")))


class KavitaSettingsProvider(CurrentStateCache):
    """Diffs Kavita's server settings (singleton, UPDATE-only)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config: dict[str, Any] = dict(config or {})
        self._session = kavita_session(self.base_url, api_key)
        self._library_ids: dict[str, int] | None = None

    def _url(self) -> str:
        return f"{self.base_url}/api/settings"

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        resp = self._session.get(self._url())
        resp.raise_for_status()
        return [resp.json() or {}]

    # -- config shaping -----------------------------------------------------
    def _library_id(self, name: str) -> int | str:
        if self._library_ids is None:
            resp = self._session.get(f"{self.base_url}/api/library/libraries")
            resp.raise_for_status()
            self._library_ids = {
                str(lib.get("name")): int(lib["id"]) for lib in resp.json() or []
            }
        if name in self._library_ids:
            return self._library_ids[name]
        log.warning(
            "Kavita: oidc.default_libraries names unknown library %r; it is kept by "
            "name until it exists (declare it under libraries: to create it first)",
            name,
        )
        return name

    def _shape(self, current: dict[str, Any]) -> dict[str, Any]:
        """The configured settings with aliases resolved, enums mapped to Kavita's
        integers, library names resolved to ids and read-only keys dropped."""
        cfg = {_ALIASES.get(k, k): v for k, v in self.config.items()}
        for key in list(cfg):
            if loose(key) in _READ_ONLY_LOOSE:
                log.warning("Kavita settings: '%s' is read-only; ignoring it", key)
                del cfg[key]
            elif not any(loose(key) == loose(k) for k in current):
                log.warning("Kavita settings: unknown setting '%s'", key)
        for path, (enum, label) in _ENUMS.items():
            if "." in path:
                continue
            for key in list(cfg):
                if loose(key) == loose(path):
                    cfg[key] = enum_value(enum, cfg[key], label)

        oidc_key = next((k for k in cfg if loose(k) == "oidcconfig"), None)
        if oidc_key is not None:
            oidc = dict(cfg[oidc_key] or {})
            if "enabled" in oidc:
                enabled = oidc.pop("enabled")
                authority = oidc.get(
                    "authority", (current.get("oidcConfig") or {}).get("authority")
                )
                if bool(enabled) != bool(authority):
                    log.warning(
                        "Kavita: oidc.enabled is derived from oidc.authority (set or "
                        "empty) and cannot be set on its own; ignoring enabled: %s",
                        enabled,
                    )
            for key in list(oidc):
                if loose(key) == "defaultagerestriction":
                    oidc[key] = enum_value(
                        AGE_RATINGS, oidc[key], "oidc.default_age_restriction"
                    )
                elif loose(key) == "defaultlibraries":
                    oidc[key] = [
                        lib if isinstance(lib, int) else self._library_id(str(lib))
                        for lib in oidc[key] or []
                    ]
            cfg[oidc_key] = oidc
        return cfg

    # -- plan ---------------------------------------------------------------
    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current = self.fetch_current()
        base = current[0] if current else {}
        desired = merge_over(base, self._shape(base))
        self._warn_restart(base, desired)
        return [desired]

    def _warn_restart(self, current: dict[str, Any], desired: dict[str, Any]) -> None:
        before, after = self.normalize(current), self.normalize(desired)
        changed = [p for p in RESTART_PATHS if before.get(p) != after.get(p)]
        if not changed:
            return
        names = ", ".join(p.split(".", 1)[1] for p in changed)
        extra = (
            " Changing the authority also unlinks every user's existing OIDC login."
            if "oidcConfig.authority" in changed
            else ""
        )
        log.warning(
            "Kavita: OIDC %s will change — Kavita only loads its OIDC settings at "
            "startup, so restart Kavita after applying.%s",
            names,
            extra,
        )

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        flat = {k: v for k, v in flatten(resource).items() if k not in READ_ONLY_PATHS}
        if _OIDC_SECRET in flat:
            flat[_OIDC_SECRET] = _secret_length_marker(flat[_OIDC_SECRET])
        if _SMTP_PASSWORD in flat:
            flat[_SMTP_PASSWORD] = fingerprint_secret(flat[_SMTP_PASSWORD])
        if isinstance(flat.get("hostName"), str):
            # Kavita trims and drops a trailing slash when it saves the host name.
            flat["hostName"] = flat["hostName"].strip().rstrip("/")
        for path, (enum, _label) in _ENUMS.items():
            if path in flat:
                flat[path] = enum_name(enum, flat[path])
        return flat

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        return Action(op=plan.op, key=plan.key, payload=dict(desired or {}))

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp = self._session.post(self._url(), json=dict(action.payload))
        resp.raise_for_status()
        self.invalidate_current()
