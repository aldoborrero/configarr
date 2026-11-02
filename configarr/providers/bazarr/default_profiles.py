"""Bazarr default-profile provider. Client-free: talks HTTP via requests.

Bazarr only searches subtitles for series and movies that carry a language profile,
and its ``serie_default_profile``/``movie_default_profile`` settings apply to items
added *after* they are set. This provider closes that gap: every series and movie
with no profile gets the one named in config.

    default_profile:
      series: "Spanish + English"
      movies: "Spanish + English"

Only items whose ``profileId`` is unset are touched; a profile chosen by hand (or by a
previous run) is never overridden, and server items are never deleted. The profile
is named, not numbered, and resolved through ``GET /api/system/languages/profiles``;
an unknown name plans nothing. Resources are keyed ``(kind, id)`` with ``kind`` in
``series``/``movies`` and ``id`` the Sonarr series id or Radarr movie id Bazarr uses.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any, cast

from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.transport import build_session

# kind -> (list/update endpoint, id field in GET /api/<kind>, form field for the id)
_KINDS = {
    "series": ("series", "sonarrSeriesId", "seriesid"),
    "movies": ("movies", "radarrId", "radarrid"),
}


class BazarrDefaultProfileProvider(CurrentStateCache):
    """Assigns the configured language profile to series/movies that have none."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.config = {k: v for k, v in (config or {}).items() if k in _KINDS and v}
        self._session = build_session()

    def _get(self, path: str) -> Any:
        resp = self._session.get(
            f"{self.base_url}/api/{path}", params={"apikey": self.api_key}
        )
        resp.raise_for_status()
        return resp.json()

    def _profile_ids(self) -> dict[str, int]:
        return {
            p.get("name"): int(p["profileId"])
            for p in self._get("system/languages/profiles") or []
            if p.get("profileId") is not None
        }

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return (resource["kind"], resource["id"])

    def _load_current(self) -> list[dict[str, Any]]:
        current: list[dict[str, Any]] = []
        for kind in self.config:
            endpoint, id_field, _ = _KINDS[kind]
            for item in (self._get(endpoint) or {}).get("data", []):
                current.append(
                    {
                        "kind": kind,
                        "id": item[id_field],
                        "title": item.get("title"),
                        "profileId": item.get("profileId"),
                    }
                )
        return current

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        ids = self._profile_ids()
        desired: list[dict[str, Any]] = []
        for item in self.fetch_current():
            profile_id = ids.get(self.config[item["kind"]])
            # Fill only what is unset; leave chosen profiles (and unknown names) alone.
            if item["profileId"] is None and profile_id is not None:
                desired.append({**item, "profileId": profile_id})
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return dict(resource)

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
        kind, item_id = cast(tuple[str, int], action.key)
        endpoint, _, id_param = _KINDS[kind]
        resp = self._session.post(
            f"{self.base_url}/api/{endpoint}",
            params={"apikey": self.api_key},
            data={id_param: item_id, "profileid": action.payload["profileId"]},
        )
        resp.raise_for_status()
        self.invalidate_current()
