"""Tranga settings (singleton). Client-free: talks HTTP via requests.

All settings are read in one ``GET /v2/Settings``, but Tranga has no bulk write:
each setting has its own endpoint (``PATCH /v2/Settings/UserAgent`` with a JSON
string body, ``PATCH /v2/Settings/BWImages/{enabled}``, …). So this provider is
over-current — desired is the current object with the configured keys overlaid —
and apply issues one call per setting that actually changed.

``max_concurrent_downloads``, ``max_concurrent_workers`` and
``work_cycle_timeout_ms`` are returned by the GET but have no write endpoint;
configuring one is an error rather than a silent no-op.
"""

from __future__ import annotations

import logging
from collections.abc import Hashable
from typing import Any
from urllib.parse import quote

from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.tranga.common import TrangaClient

log = logging.getLogger(__name__)

# config key -> TrangaSettings field (GET /v2/Settings).
FIELDS: dict[str, str] = {
    "user_agent": "userAgent",
    "image_compression": "imageCompression",
    "black_white_images": "blackWhiteImages",
    "flaresolverr_url": "flareSolverrUrl",
    "chapter_naming_scheme": "chapterNamingScheme",
    "download_language": "downloadLanguage",
    "library_refresh_setting": "libraryRefreshSetting",
    "refresh_library_while_downloading_every_minutes": (
        "refreshLibraryWhileDownloadingEveryMinutes"
    ),
}
# Returned by GET but not writable through the API.
READ_ONLY: frozenset[str] = frozenset(
    {"max_concurrent_downloads", "max_concurrent_workers", "work_cycle_timeout_ms"}
)
LIBRARY_REFRESH_SETTINGS: tuple[str, ...] = (
    "AfterAllFinished",
    "AfterMangaFinished",
    "AfterEveryChapter",
    "WhileDownloading",
)
# Both written by one PATCH /v2/Settings/LibraryRefresh.
_LIBRARY_REFRESH = (
    "libraryRefreshSetting",
    "refreshLibraryWhileDownloadingEveryMinutes",
)
_SINGLETON = "settings"


def _canonical_refresh(value: Any) -> str:
    for name in LIBRARY_REFRESH_SETTINGS:
        if str(value).replace("_", "").lower() == name.lower():
            return name
    raise ValueError(
        f"Tranga: unknown library_refresh_setting '{value}' "
        f"(expected one of {', '.join(LIBRARY_REFRESH_SETTINGS)})"
    )


class TrangaSettingsProvider(TrangaClient, CurrentStateCache):
    """Diffs Tranga's settings object (singleton, UPDATE-only)."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config: dict[str, Any] = config or {}
        read_only = sorted(k for k in self.config if k in READ_ONLY)
        if read_only:
            raise ValueError(
                f"Tranga settings: {', '.join(read_only)} cannot be set through "
                "the Tranga API"
            )
        image = self.config.get("image_compression")
        if image is not None and not 1 <= int(image) <= 100:
            raise ValueError("Tranga settings: image_compression must be 1..100")

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current = self._request("GET", "/v2/Settings").json() or {}
        return [{f: current.get(f) for f in FIELDS.values()}]

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        unknown = sorted(k for k in self.config if k not in FIELDS)
        if unknown:
            log.warning(
                "Tranga settings: ignoring unknown setting(s): %s", ", ".join(unknown)
            )
        current = self.fetch_current()
        obj = dict(current[0]) if current else {}
        for key, field in FIELDS.items():
            if key not in self.config or self.config[key] is None:
                continue
            value = self.config[key]
            if field == "libraryRefreshSetting":
                value = _canonical_refresh(value)
            obj[field] = value
        return [obj]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        out = {f: coerce_scalar(resource.get(f)) for f in FIELDS.values()}
        # Tranga stores an unset FlareSolverr URL as "".
        if out["flareSolverrUrl"] is None:
            out["flareSolverrUrl"] = ""
        return out

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        desired = desired or {}
        cur = self.normalize(current or {})
        des = self.normalize(desired)
        changed = {f: desired.get(f) for f in FIELDS.values() if cur[f] != des[f]}
        # LibraryRefresh writes both fields at once; send the pair together.
        if any(f in changed for f in _LIBRARY_REFRESH):
            for f in _LIBRARY_REFRESH:
                changed[f] = desired.get(f)
        return Action(op=plan.op, key=plan.key, payload=changed)

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        p = action.payload
        if "userAgent" in p:
            self._request("PATCH", "/v2/Settings/UserAgent", json=p["userAgent"])
        if "imageCompression" in p:
            level = int(p["imageCompression"])
            self._request("PATCH", f"/v2/Settings/ImageCompressionLevel/{level}")
        if "blackWhiteImages" in p:
            enabled = "true" if coerce_scalar(p["blackWhiteImages"]) else "false"
            self._request("PATCH", f"/v2/Settings/BWImages/{enabled}")
        if "flareSolverrUrl" in p:
            if p["flareSolverrUrl"]:
                self._request(
                    "PATCH", "/v2/Settings/FlareSolverr/Url", json=p["flareSolverrUrl"]
                )
            else:
                self._request("DELETE", "/v2/Settings/FlareSolverr/Url")
        if "chapterNamingScheme" in p:
            self._request(
                "PATCH",
                "/v2/Settings/ChapterNamingScheme",
                json=p["chapterNamingScheme"],
            )
        if "downloadLanguage" in p:
            lang = quote(str(p["downloadLanguage"]), safe="")
            self._request("PATCH", f"/v2/Settings/DownloadLanguage/{lang}")
        if "libraryRefreshSetting" in p:
            body: dict[str, Any] = {"setting": p["libraryRefreshSetting"]}
            minutes = p.get("refreshLibraryWhileDownloadingEveryMinutes")
            if minutes is not None:
                body["refreshLibraryWhileDownloadingEveryMinutes"] = int(minutes)
            self._request("PATCH", "/v2/Settings/LibraryRefresh", json=body)
        self.invalidate_current()
