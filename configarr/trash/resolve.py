"""Expand each instance's ``trash:`` block into its own custom formats and quality
definitions, in place, after parsing.

This is the whole point of the design: TRaSH is a config-expansion concern, not a
provider concern. Everything here writes into the same internal structures a
hand-written config produces (``instance.custom_formats``,
``quality_profiles[].custom_format_scores``, ``instance.quality_definitions``), so
``CustomFormatProvider`` / ``QualityProfileProvider`` / ``QualityDefinitionProvider``
— and the diff engine — need no knowledge of TRaSH. User-authored definitions always
win over imported ones.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from configarr.models import (
    ArrServiceConfig,
    ConfigarrConfig,
    TrashCustomFormatGroup,
    TrashScoreTarget,
)
from configarr.trash.catalog import Catalog, TrashCustomFormat
from configarr.trash.metadata import load_metadata
from configarr.trash.source import resolve_source

log = logging.getLogger("configarr.trash")

DEFAULT_SCORE_SET = "default"


def resolve_trash(
    config: ConfigarrConfig,
    base_dir: Path,
    service: str | None = None,
    instance: str | None = None,
) -> None:
    """Resolve every in-scope Radarr/Sonarr instance that declares a ``trash:``
    block. ``service``/``instance`` mirror the CLI filters so an out-of-scope
    instance's guide is never read."""
    svc_filter = service.lower() if service else None
    for svc, instances in (("radarr", config.radarr), ("sonarr", config.sonarr)):
        if svc_filter and svc != svc_filter:
            continue
        for inst in instances:
            if instance and inst.name != instance:
                continue
            if inst.trash is not None:
                _resolve_instance(svc, inst, base_dir)


def _resolve_instance(service: str, instance: ArrServiceConfig, base_dir: Path) -> None:
    trash = instance.trash
    assert trash is not None  # guarded by the caller
    root = resolve_source(trash, base_dir)
    json_paths = load_metadata(root).json_paths
    paths = json_paths.radarr if service == "radarr" else json_paths.sonarr
    catalog = Catalog(root, paths)

    for group in trash.custom_formats:
        _import_group(instance, catalog, group)

    if trash.quality_definition:
        _import_quality_definition(instance, catalog, trash.quality_definition)


def _import_group(
    instance: ArrServiceConfig, catalog: Catalog, group: TrashCustomFormatGroup
) -> None:
    for trash_id in group.trash_ids:
        cf = catalog.custom_format(trash_id)
        _add_custom_format(instance, cf)
        for target in group.assign_scores_to:
            _assign_score(instance, cf, target)


def _add_custom_format(instance: ArrServiceConfig, cf: TrashCustomFormat) -> None:
    name = cf["name"]
    if name in instance.custom_formats:
        log.debug("trash: custom format %r already in config; keeping user copy", name)
        return
    instance.custom_formats[name] = {
        "specifications": cf["specifications"],
        "include_when_renaming": cf["include_when_renaming"],
    }


def _assign_score(
    instance: ArrServiceConfig, cf: TrashCustomFormat, target: TrashScoreTarget
) -> None:
    profile = _find_profile(instance.quality_profiles, target.profile)
    if profile is None:
        log.warning(
            "trash: quality profile %r not found for scoring custom format %r",
            target.profile,
            cf["name"],
        )
        return
    scores: dict[str, Any] = profile.setdefault("custom_format_scores", {})
    if cf["name"] in scores:
        log.debug(
            "trash: score for %r already set on profile %r; keeping user value",
            cf["name"],
            target.profile,
        )
        return
    scores[cf["name"]] = _score_for(cf, target)


def _score_for(cf: TrashCustomFormat, target: TrashScoreTarget) -> int:
    if target.score is not None:
        return target.score
    requested = target.score_set or DEFAULT_SCORE_SET
    # Score sets are matched case-insensitively, and a missing named set falls back
    # to "default" before giving up — both match recyclarr's DetermineScore.
    scores = {k.lower(): v for k, v in cf["trash_scores"].items()}
    if requested.lower() in scores:
        return scores[requested.lower()]
    if requested.lower() != DEFAULT_SCORE_SET and DEFAULT_SCORE_SET in scores:
        log.warning(
            "trash: custom format %r has no score set %r; using 'default'",
            cf["name"],
            requested,
        )
        return scores[DEFAULT_SCORE_SET]
    log.warning(
        "trash: custom format %r has no score set %r; scoring 0 into profile %r",
        cf["name"],
        requested,
        target.profile,
    )
    return 0


def _find_profile(profiles: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for profile in profiles:
        if profile.get("name") == name:
            return profile
    return None


def _import_quality_definition(
    instance: ArrServiceConfig, catalog: Catalog, type_name: str
) -> None:
    resolved = catalog.quality_definition(type_name)
    # User-authored quality definitions win over imported ones.
    instance.quality_definitions = {**resolved, **(instance.quality_definitions or {})}
