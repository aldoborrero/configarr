"""Generic, service-agnostic differ."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any

from configarr.model import FieldDiff, Op, Plan, ResourcePlan


def reconcile_renames(
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    managed_ids: dict[str, int],
    *,
    name_key: str = "name",
    id_key: str = "id",
) -> tuple[list[dict[str, Any]], set[Any]]:
    """Relabel server-renamed managed resources so a name-based diff recognizes them.

    ``managed_ids`` maps a name configarr manages to the service id it created. If a
    desired name is missing from ``current`` by name but its recorded id still exists
    on the server (under a different name), that resource was renamed out-of-band;
    relabel a copy of it to the desired name so the diff updates it in place (renaming
    it back) instead of creating a duplicate.

    Returns ``(current, renamed)``: a list usable in place of ``current`` (entries
    copied only when relabeled), and the set of desired names that were relabeled.
    Because relabeling makes the name match, the name change itself no longer shows
    as a field diff — callers pass ``renamed`` to ``diff(force_update=...)`` so the
    rename is still applied when nothing else changed.
    """
    if not managed_ids:
        return current, set()
    by_name = {r.get(name_key) for r in current}
    by_id = {r[id_key]: r for r in current if id_key in r}
    desired_names = {d.get(name_key) for d in desired}
    remapped: dict[int, Any] = {}
    for name in desired_names:
        if name in by_name or not isinstance(name, str):
            continue
        sid = managed_ids.get(name)
        if sid is None:
            continue
        candidate = by_id.get(sid)
        # Don't steal a resource that legitimately matches another desired name.
        if candidate is not None and candidate.get(name_key) not in desired_names:
            remapped[sid] = name
    if not remapped:
        return current, set()
    reconciled = [
        {**r, name_key: remapped[r[id_key]]} if r.get(id_key) in remapped else r
        for r in current
    ]
    return reconciled, set(remapped.values())


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
    force_update: set[Hashable] | None = None,
) -> Plan:
    force_update = force_update or set()
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
        # force_update carries keys that must be written even without a field diff —
        # e.g. a resource relabeled by rename reconciliation, whose only change (the
        # name) matching hid, still needs the write to rename it back on the server.
        changed = bool(fds) or key in force_update
        plans.append(
            ResourcePlan(kind, key, Op.UPDATE if changed else Op.UNCHANGED, fds)
        )
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
