"""Metadata-profile provider (Bookshelf / Readarr only). Client-free: talks HTTP via
requests.

A metadata profile filters which books an author brings in (popularity, page
count, languages, ISBN/date presence, parts and sets, secondary series). Readarr
has no equivalent in Radarr/Sonarr, so this is its own provider on ``/api/v1``.

Matched by name; full-replace (PUT carries the whole object), so build_desired
merges the configured fields over current, or over ``/metadataprofile/schema`` on
create. ``allowed_languages`` is a list in config and a comma-separated string in
the API (``"spa,eng"``); it is compared as a set.

Prunable, with two server rules surfaced rather than tripped over:

- the built-in ``None`` profile is reserved (Readarr refuses to edit or delete it),
  so it is dropped from current and never planned;
- Readarr refuses to delete a profile still used by an author, an import list or a
  root folder's default (``MetadataProfileInUseException``, HTTP 400). That error is
  re-raised with the profile name and the reason, instead of a bare 400.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

import requests

from configarr.build import merge_full_replace
from configarr.normalize import coerce_scalar
from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, HttpProvider

# The reserved built-in profile (MetadataProfileService.NONE_PROFILE_NAME).
NONE_PROFILE = "None"

# config key -> API field.
_FIELD_MAP = {
    "min_popularity": "minPopularity",
    "skip_missing_date": "skipMissingDate",
    "skip_missing_isbn": "skipMissingIsbn",
    "skip_parts_and_sets": "skipPartsAndSets",
    "skip_series_secondary": "skipSeriesSecondary",
    "allowed_languages": "allowedLanguages",
    "min_pages": "minPages",
    "ignored": "ignored",
}


def _languages(value: Any) -> str:
    """A config ``allowed_languages`` (list or comma string) as the API's string."""
    if isinstance(value, str):
        return value
    return ",".join(str(v) for v in value or [])


def _language_set(value: Any) -> list[str]:
    """The API's comma-separated languages as a sorted list, for comparison."""
    if not value:
        return []
    return sorted({part.strip() for part in str(value).split(",") if part.strip()})


class MetadataProfileProvider(HttpProvider):
    """Diffs Bookshelf metadata profiles by name (full-replace, prunable)."""

    full_replace = True
    prunable = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: Any,
        kind: str,
        api_prefix: str | None = "/api/v1",
    ):
        super().__init__(base_url, api_key, api_prefix)
        self.kind = kind
        self.config = config or {}
        self._schema_cache: dict[str, Any] | None = None

    def _schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            self._schema_cache = self._get(
                f"{self.api_prefix}/metadataprofile/schema"
            ).json()
        return self._schema_cache

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get(
            f"{self.api_prefix}/metadataprofile"
        ).json()
        return [p for p in data if p.get("name") != NONE_PROFILE]

    @staticmethod
    def _overrides(definition: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for cfg_key, api_field in _FIELD_MAP.items():
            if cfg_key in definition:
                out[api_field] = definition[cfg_key]
        if "allowedLanguages" in out:
            out["allowedLanguages"] = _languages(out["allowedLanguages"])
        if "ignored" in out:
            out["ignored"] = list(out["ignored"] or [])
        return out

    def build_desired(self) -> list[dict[str, Any]]:
        if not self.config:
            return []
        current_by_name = {self.match_key(c): c for c in self.fetch_current()}
        desired: list[dict[str, Any]] = []
        for name, definition in self.config.items():
            if name == NONE_PROFILE:
                raise ValueError(
                    f"metadata profile {NONE_PROFILE!r} is reserved by Bookshelf and "
                    "cannot be managed; give the profile another name"
                )
            if definition is not None and not isinstance(definition, dict):
                raise ValueError(
                    f"metadata profile {name!r} must be a mapping of settings"
                )
            overrides = {"name": name, **self._overrides(definition or {})}
            current = current_by_name.get(name)
            if current is None:
                schema = {k: v for k, v in self._schema().items() if k != "id"}
                desired.append(merge_full_replace(schema, None, overrides))
            else:
                desired.append(merge_full_replace({}, current, overrides))
        return desired

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        out = {
            api: coerce_scalar(resource.get(api))
            for api in _FIELD_MAP.values()
            if api not in ("allowedLanguages", "ignored", "minPopularity")
        }
        # minPopularity is a double server-side: 0 and 0.0 are the same value.
        popularity = resource.get("minPopularity")
        out["minPopularity"] = float(popularity) if popularity is not None else None
        out["allowedLanguages"] = _language_set(resource.get("allowedLanguages"))
        out["ignored"] = sorted(resource.get("ignored") or [])
        return out

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE, Op.DELETE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        if plan.op is Op.CREATE:
            payload = {k: v for k, v in (desired or {}).items() if k != "id"}
            return Action(op=plan.op, key=plan.key, payload=payload)
        if plan.op is Op.DELETE:
            assert current is not None, (
                f"to_action: DELETE for {plan.key!r} requires the current resource"
            )
            return Action(
                op=plan.op,
                key=plan.key,
                payload={"id": current["id"], "name": current.get("name")},
            )
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> int | None:
        path = f"{self.api_prefix}/metadataprofile"
        service_id: int | None = None
        if action.op is Op.CREATE:
            created = self._post(path, json=action.payload).json()
            service_id = created.get("id") if isinstance(created, dict) else None
        elif action.op is Op.UPDATE:
            service_id = action.payload["id"]
            self._put(f"{path}/{service_id}", json=action.payload)
        elif action.op is Op.DELETE:
            self._delete_profile(path, action.payload)
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
        return service_id

    def _delete_profile(self, path: str, payload: dict[str, Any]) -> None:
        try:
            self._delete(f"{path}/{payload['id']}")
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 400:
                raise
            raise RuntimeError(
                f"cannot delete metadata profile {payload.get('name')!r}: "
                f"{_server_message(exc.response)} — Bookshelf refuses to delete a "
                "profile still used by an author, an import list or a root "
                "folder's default; reassign those first or keep it in the config"
            ) from exc


def _server_message(response: requests.Response) -> str:
    """The ``message`` of a Readarr error body, else the raw text."""
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(body, dict) and body.get("message"):
        return str(body["message"])
    return response.text or f"HTTP {response.status_code}"
