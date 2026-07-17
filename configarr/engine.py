"""Generic, service-agnostic differ."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any

from configarr.model import FieldDiff, Op, Plan, ResourcePlan


def _field_diffs(before: dict[str, Any], after: dict[str, Any]) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    # Only desired keys drive updates; absent desired keys are left to the
    # provider's build_desired (which already merged defaults/current).
    for key in after:
        if before.get(key) != after[key]:
            diffs.append(FieldDiff(path=key, before=before.get(key), after=after[key]))
    return diffs


def _current_only_diffs(
    before: dict[str, Any], after: dict[str, Any]
) -> list[FieldDiff]:
    # Full-replace apply PUTs the whole desired object, so any key in the normalized
    # current but absent from desired would be reset on the server. Surface these so
    # a plan can't report UNCHANGED while apply silently mutates state. A provider
    # that merges desired over current (Phase A5) carries every current key and never
    # trips this guard.
    return [
        FieldDiff(path=key, before=before[key], after=None)
        for key in before
        if key not in after
    ]


def _index(
    items: list[dict[str, Any]],
    match_key: Callable[[dict[str, Any]], Hashable],
    side: str,
) -> dict[Hashable, dict[str, Any]]:
    out: dict[Hashable, dict[str, Any]] = {}
    for r in items:
        k = match_key(r)
        if k in out:
            raise ValueError(f"duplicate key in {side}: {k!r}")
        out[k] = r
    return out


def diff(
    kind: str,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    match_key: Callable[[dict[str, Any]], Hashable],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    full_replace: bool = False,
    prune: bool = False,
    managed_keys: set[Hashable] | None = None,
) -> Plan:
    cur_by_key = _index(current, match_key, "current")
    des_by_key = _index(desired, match_key, "desired")
    plans: list[ResourcePlan] = []
    for d in desired:
        key = match_key(d)
        nd = normalize(d)
        if key not in cur_by_key:
            plans.append(ResourcePlan(kind, key, Op.CREATE, _field_diffs({}, nd)))
            continue
        nc = normalize(cur_by_key[key])
        fds = _field_diffs(nc, nd)
        if full_replace:
            fds = fds + _current_only_diffs(nc, nd)
        plans.append(ResourcePlan(kind, key, Op.UPDATE if fds else Op.UNCHANGED, fds))
    if prune:
        # Opt-in deletion of a current resource the config no longer declares.
        # ``managed_keys`` scopes this to ownership: when supplied, only resources
        # configarr previously created (recorded in state) are deletable, so a
        # user-created resource is never pruned. ``None`` keeps the legacy
        # delete-any-unmanaged behavior for callers without state.
        for key in cur_by_key:
            if key in des_by_key:
                continue
            if managed_keys is not None and key not in managed_keys:
                continue
            plans.append(ResourcePlan(kind, key, Op.DELETE))
    return Plan(resources=plans)
