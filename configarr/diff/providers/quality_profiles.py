"""Quality-profile provider (Radarr/Sonarr share the API). Client-free: talks
HTTP via requests.

Full-replace resource: a PUT replaces the whole object, so build_desired merges
the config-derived profile over current over the ``/qualityprofile/schema``
defaults. The schema lists every quality (in semantic priority order) and one
FormatItem per existing custom format, which the server's validators require to
be exactly complete — building from it keeps both invariants for free.
"""

from __future__ import annotations

import copy
from typing import Any, Hashable

import requests

from configarr.diff.build import merge_full_replace
from configarr.diff.model import Op, ResourcePlan
from configarr.diff.providers.base import Action, CurrentStateCache


class QualityProfileProvider(CurrentStateCache):
    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config = config or []
        self._session = requests.Session()
        self._session.headers["X-Api-Key"] = api_key
        self._schema_cache: dict[str, Any] | None = None
        self._language_cache: list[dict[str, Any]] | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            resp = self._session.get(self._url("/api/v3/qualityprofile/schema"))
            resp.raise_for_status()
            self._schema_cache = resp.json()
        return self._schema_cache

    def _resolve_language(self, name: str) -> dict[str, Any] | None:
        """Resolve a language name (e.g. 'Original', 'Any', 'English') to a
        ``{id, name}`` object via ``/api/v3/language``. Returns None when the
        name cannot be matched, in which case the caller leaves the profile's
        language untouched (falling back to current/schema).
        """
        if self._language_cache is None:
            resp = self._session.get(self._url("/api/v3/language"))
            resp.raise_for_status()
            self._language_cache = resp.json()
        for lang in self._language_cache:
            lang_name = lang.get("name")
            if lang_name and lang_name.lower() == name.lower():
                return {"id": lang["id"], "name": lang_name}
        return None

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        name: str = resource["name"]
        return name

    def _load_current(self) -> list[dict[str, Any]]:
        resp = self._session.get(self._url("/api/v3/qualityprofile"))
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()
        return data

    @staticmethod
    def _enabled_names(profile: dict[str, Any]) -> set[str]:
        enabled: set[str] = set()
        for q in profile.get("qualities", []):
            if not isinstance(q, dict):
                enabled.add(q)
                continue
            if not q.get("enabled", True):
                continue
            enabled.add(q["name"])
            for nested in q.get("qualities", []):
                enabled.add(nested)
        return enabled

    def _build_items(
        self, schema_items: list[dict[str, Any]], enabled: set[str]
    ) -> list[dict[str, Any]]:
        # Preserve the schema's order (semantic priority); only flip `allowed`.
        out: list[dict[str, Any]] = []
        for item in schema_items:
            quality = item.get("quality")
            if quality is not None:
                out.append({**item, "allowed": quality.get("name") in enabled})
            else:
                children = self._build_items(item.get("items", []), enabled)
                group_allowed = item.get("name") in enabled or any(
                    c["allowed"] for c in children
                )
                out.append({**item, "items": children, "allowed": group_allowed})
        return out

    @staticmethod
    def _resolve_cutoff(
        items: list[dict[str, Any]], cutoff_name: str | None, default: Any
    ) -> Any:
        if cutoff_name is None:
            return default
        for item in items:
            quality = item.get("quality")
            if quality is not None:
                if quality.get("name") == cutoff_name:
                    return quality.get("id")
            else:
                if item.get("name") == cutoff_name:
                    return item.get("id")
                for child in item.get("items", []):
                    cq = child.get("quality")
                    if cq is not None and cq.get("name") == cutoff_name:
                        return cq.get("id")
        return default

    def _build_profile(
        self, profile: dict[str, Any], current: dict[str, Any] | None
    ) -> dict[str, Any]:
        schema = copy.deepcopy(self._schema())
        enabled = self._enabled_names(profile)
        items = self._build_items(schema.get("items", []), enabled)
        upgrade = profile.get("upgrade") or {}
        cutoff = self._resolve_cutoff(
            items, upgrade.get("until_quality"), schema.get("cutoff")
        )
        scores = profile.get("custom_format_scores") or {}
        format_items = [
            {**fi, "score": scores.get(fi.get("name"), 0)}
            for fi in schema.get("formatItems", [])
        ]
        built: dict[str, Any] = {
            "name": profile["name"],
            "upgradeAllowed": upgrade.get("allowed", True),
            "cutoff": cutoff,
            "items": items,
            "minFormatScore": profile.get("min_format_score", 0),
            "cutoffFormatScore": upgrade.get("until_score", 10000),
            "minUpgradeFormatScore": 1,
            "formatItems": format_items,
        }
        # Radarr quality profiles carry a language filter (Sonarr's do not).
        # When unset Radarr rejects every release with "<blank> is wanted, but
        # found <lang>"; resolve the configured name and include it so the diff
        # reflects the user's intent. An unresolved name leaves it to fall back
        # to the current/schema language via merge_full_replace.
        language_name = profile.get("language")
        if language_name and self.kind.startswith("radarr"):
            language = self._resolve_language(language_name)
            if language is not None:
                built["language"] = language
        return merge_full_replace(schema, current, built)

    def build_desired(self) -> list[dict[str, Any]]:
        current_by_name = {c["name"]: c for c in self.fetch_current()}
        return [
            self._build_profile(profile, current_by_name.get(profile["name"]))
            for profile in self.config
        ]

    def _norm_item(self, item: dict[str, Any]) -> dict[str, Any]:
        quality = item.get("quality")
        if quality is not None:
            # Compare qualities by id; drop the server-echoed label.
            return {
                "allowed": bool(item.get("allowed", False)),
                "id": quality.get("id"),
            }
        return {
            "allowed": bool(item.get("allowed", False)),
            "group": item.get("id"),
            "items": [self._norm_item(c) for c in item.get("items", [])],
        }

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        language = resource.get("language")
        format_items = sorted(
            (
                {"format": fi.get("format"), "score": fi.get("score", 0)}
                for fi in resource.get("formatItems", [])
            ),
            key=lambda fi: (fi["format"] is None, fi["format"]),
        )
        return {
            "upgradeAllowed": bool(resource.get("upgradeAllowed", False)),
            "cutoff": resource.get("cutoff"),
            "minFormatScore": resource.get("minFormatScore", 0),
            "cutoffFormatScore": resource.get("cutoffFormatScore", 0),
            "minUpgradeFormatScore": resource.get("minUpgradeFormatScore", 1),
            # `items` order is semantic (priority) — do not sort.
            "items": [self._norm_item(i) for i in resource.get("items", [])],
            "formatItems": format_items,
            "language": (language or {}).get("id") if language else None,
        }

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        if plan.op is Op.CREATE:
            payload = {k: v for k, v in (desired or {}).items() if k != "id"}
            return Action(op=plan.op, key=plan.key, payload=payload)
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action: Action) -> None:
        if action.op is Op.CREATE:
            resp = self._session.post(
                self._url("/api/v3/qualityprofile"), json=action.payload
            )
        elif action.op is Op.UPDATE:
            qp_id = action.payload["id"]
            resp = self._session.put(
                self._url(f"/api/v3/qualityprofile/{qp_id}"), json=action.payload
            )
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        resp.raise_for_status()
        self.invalidate_current()
