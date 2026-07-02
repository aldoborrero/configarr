"""Quality-profile provider (Radarr/Sonarr share the API). Client-free: talks
HTTP via requests.

Full-replace resource: a PUT replaces the whole object, so build_desired merges
the config-derived profile over current over the ``/qualityprofile/schema``
defaults.

Quality *items* are built from the config's ``qualities`` list, which drives both
the enabled set and the **priority order** (top = highest) and may define custom
quality **groups** (`{name, qualities: [...]}`). Qualities the config doesn't list
are appended disabled at the bottom, so the server's completeness validator is
satisfied. This mirrors recyclarr's ``QualityItemOrganizer`` (see
``.scratch/recyclarr``); building from the *current* profile when it exists keeps
server-assigned group ids stable across re-plans.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Hashable, Iterator
from typing import Any

from configarr.build import merge_full_replace
from configarr.model import Op, ResourcePlan
from configarr.providers.base import Action, HttpProvider

log = logging.getLogger("configarr.quality_profile")


def _normalize_config_quality(quality: Any) -> dict[str, Any]:
    """A config `qualities` entry (a bare name or `{name, qualities, enabled}`)
    in a uniform shape."""
    if isinstance(quality, str):
        return {"name": quality, "qualities": [], "enabled": True}
    return {
        "name": quality["name"],
        "qualities": list(quality.get("qualities") or []),
        "enabled": quality.get("enabled", True),
    }


def _flatten(items: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for item in items:
        yield item
        yield from _flatten(item.get("items") or [])


def _find_quality(source: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    low = name.lower()
    for item in _flatten(source):
        quality = item.get("quality")
        if quality is not None and (quality.get("name") or "").lower() == low:
            return item
    return None


def _find_group(source: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    low = name.lower()
    for item in _flatten(source):
        if item.get("quality") is None and (item.get("name") or "").lower() == low:
            return item
    return None


def _new_item_id(items: list[dict[str, Any]]) -> int:
    # Mirrors Radarr's frontend: group ids start at 1001 (max(1000, max id) + 1).
    ids = [int(i["id"]) for i in _flatten(items) if i.get("id") is not None]
    return max([1000, *ids]) + 1


def _quality_name(item: dict[str, Any]) -> str:
    return ((item.get("quality") or {}).get("name") or "").lower()


class QualityProfileProvider(HttpProvider):
    """Diffs Radarr/Sonarr quality profiles by name (full-replace)."""

    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str):
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config = config or []
        self._schema_cache: dict[str, Any] | None = None
        self._language_cache: list[dict[str, Any]] | None = None

    def _schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            self._schema_cache = self._get("/api/v3/qualityprofile/schema").json()
        return self._schema_cache

    def _resolve_language(self, name: str) -> dict[str, Any] | None:
        """Resolve a language name (e.g. 'Original', 'Any', 'English') to a
        ``{id, name}`` object via ``/api/v3/language``. Returns None when the
        name cannot be matched, in which case the caller leaves the profile's
        language untouched (falling back to current/schema).
        """
        if self._language_cache is None:
            self._language_cache = self._get("/api/v3/language").json()
        for lang in self._language_cache:
            lang_name = lang.get("name")
            if lang_name and lang_name.lower() == name.lower():
                return {"id": lang["id"], "name": lang_name}
        return None

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        name: str = resource["name"]
        return name

    def _load_current(self) -> list[dict[str, Any]]:
        data: list[dict[str, Any]] = self._get("/api/v3/qualityprofile").json()
        return data

    def _wanted_items(
        self, source: list[dict[str, Any]], config_qualities: list[Any]
    ) -> tuple[list[dict[str, Any]], set[str], set[str]]:
        """Build the enabled items in config (priority) order, resolving names and
        group members against ``source``. Returns the items plus the sets of
        wanted quality/group names (lower-cased) for the unwanted pass."""
        wanted: list[dict[str, Any]] = []
        wanted_qualities: set[str] = set()
        wanted_groups: set[str] = set()
        invalid: list[str] = []

        for cq in (_normalize_config_quality(q) for q in config_qualities):
            enabled = cq["enabled"]
            if cq["qualities"]:  # a quality group
                members: list[dict[str, Any]] = []
                for child in cq["qualities"]:
                    leaf = _find_quality(source, child)
                    if leaf is None:
                        invalid.append(child)
                        continue
                    members.append({**leaf, "allowed": enabled})
                    wanted_qualities.add(child.lower())
                group: dict[str, Any] = {
                    "name": cq["name"],
                    "allowed": enabled,
                    "items": members,
                }
                existing = _find_group(source, cq["name"])
                if existing is not None and existing.get("id") is not None:
                    group["id"] = existing["id"]  # reuse the server's group id
                wanted.append(group)
                wanted_groups.add(cq["name"].lower())
            else:  # a single quality
                leaf = _find_quality(source, cq["name"])
                if leaf is None:
                    invalid.append(cq["name"])
                    continue
                wanted.append({**leaf, "allowed": enabled})
                wanted_qualities.add(cq["name"].lower())

        if invalid:
            log.warning(
                "quality profile: qualities not offered by %s, ignored: %s",
                self.kind,
                ", ".join(invalid),
            )
        return wanted, wanted_qualities, wanted_groups

    @staticmethod
    def _unwanted_items(
        source: list[dict[str, Any]],
        wanted_qualities: set[str],
        wanted_groups: set[str],
    ) -> list[dict[str, Any]]:
        """Every source quality not already wanted, appended as disabled — kept in
        its source group unless the group itself was wanted, with singleton groups
        flattened and empty groups dropped (recyclarr's GetUnwantedItems)."""

        def keep(item: dict[str, Any]) -> list[dict[str, Any]]:
            if item.get("quality") is not None:  # leaf
                return [] if _quality_name(item) in wanted_qualities else [item]
            leftover = [
                c
                for c in (item.get("items") or [])
                if _quality_name(c) not in wanted_qualities
            ]
            if (item.get("name") or "").lower() in wanted_groups:
                return leftover  # group is wanted; float out only its extras
            return [{**item, "items": leftover}]

        disabled: list[dict[str, Any]] = []
        for item in source:
            for kept in keep(item):
                kept = {**kept, "allowed": False}
                if kept.get("quality") is None:
                    kept["items"] = [
                        {**c, "allowed": False} for c in (kept.get("items") or [])
                    ]
                disabled.append(kept)

        result: list[dict[str, Any]] = []
        for item in disabled:
            children = item.get("items") or []
            if item.get("quality") is None and len(children) == 1:
                result.append(children[0])  # flatten singleton group
            elif item.get("quality") is None and not children:
                continue  # drop now-empty group
            else:
                result.append(item)
        return result

    @staticmethod
    def _assign_group_ids(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        next_id = _new_item_id(items)
        out: list[dict[str, Any]] = []
        for item in items:
            if item.get("quality") is None and item.get("id") is None:
                out.append({**item, "id": next_id})
                next_id += 1
            else:
                out.append(item)
        return out

    def _organize_items(
        self, source: list[dict[str, Any]], profile: dict[str, Any]
    ) -> list[dict[str, Any]]:
        wanted, wanted_q, wanted_g = self._wanted_items(
            source, profile.get("qualities") or []
        )
        unwanted = self._unwanted_items(source, wanted_q, wanted_g)
        combined = (
            unwanted + wanted
            if profile.get("quality_sort") == "bottom"
            else wanted + unwanted
        )
        return self._assign_group_ids(combined)

    @staticmethod
    def _resolve_cutoff(
        items: list[dict[str, Any]], cutoff_name: str | None, default: Any
    ) -> Any:
        """Cutoff resolves to the id of an *allowed* quality or group by name."""
        if cutoff_name is None:
            return default
        low = cutoff_name.lower()
        for item in _flatten(items):
            if not item.get("allowed"):
                continue
            quality = item.get("quality")
            if quality is not None:
                if (quality.get("name") or "").lower() == low:
                    return quality.get("id")
            elif (item.get("name") or "").lower() == low:
                return item.get("id")
        return default

    def _build_profile(
        self, profile: dict[str, Any], current: dict[str, Any] | None
    ) -> dict[str, Any]:
        schema = copy.deepcopy(self._schema())
        # Organize against the current profile (stable group ids) or the schema.
        source = current["items"] if current else schema.get("items", [])
        items = self._organize_items(source, profile)
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
            self._post("/api/v3/qualityprofile", json=action.payload)
        elif action.op is Op.UPDATE:
            qp_id = action.payload["id"]
            self._put(f"/api/v3/qualityprofile/{qp_id}", json=action.payload)
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
