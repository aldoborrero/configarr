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
    key: Callable[[dict[str, Any]], Hashable] | None = None,
) -> tuple[list[dict[str, Any]], set[Any]]:
    """Relabel server-renamed managed resources so a name-based diff recognizes them.

    ``managed_ids`` maps a match key configarr manages to the service id it created.
    When a desired resource is gone by match key but its recorded id still exists
    under a different name, relabel that entry to the desired name so the diff renames
    it in place instead of creating a duplicate.

    ``key`` is the provider's ``match_key``; pass it whenever the match key isn't the
    raw name (e.g. the case-insensitive Prowlarr provider) or the id lookup misses.

    Returns ``(current, renamed)`` where ``renamed`` is the set of match keys
    relabeled — callers pass it to ``diff(force_update=...)`` so the rename still
    applies when nothing else changed.
    """
    if not managed_ids:
        return current, set()
    if key is None:
        key = lambda r: r.get(name_key)  # noqa: E731
    present = {key(r) for r in current}
    by_id = {r[id_key]: r for r in current if id_key in r}
    desired_keys = {key(d) for d in desired}
    remapped: dict[int, Any] = {}  # sid -> raw name to relabel the current entry to
    renamed: set[Hashable] = set()  # match keys forced to UPDATE (name change hid)
    for d in desired:
        mk = key(d)
        if mk in present or not isinstance(mk, str):
            continue
        sid = managed_ids.get(mk)
        if sid is None:
            continue
        candidate = by_id.get(sid)
        # Don't steal a resource that legitimately matches another desired resource.
        if candidate is not None and key(candidate) not in desired_keys:
            remapped[sid] = d.get(name_key)
            renamed.add(mk)
    if not remapped:
        return current, set()
    reconciled = [
        {**r, name_key: remapped[r[id_key]]} if r.get(id_key) in remapped else r
        for r in current
    ]
    return reconciled, renamed


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
    kind: str,
) -> dict[Hashable, dict[str, Any]]:
    out: dict[Hashable, dict[str, Any]] = {}
    for r in items:
        k = match_key(r)
        if k in out:
            what = "two nameless resources" if k is None else f"the name {k!r}"
            raise ValueError(
                f"{kind}: {side} has {what} sharing one identity — rename or remove one"
            )
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
    cur_by_key = _index(current, match_key, "current", kind)
    des_by_key = _index(desired, match_key, "desired", kind)
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
