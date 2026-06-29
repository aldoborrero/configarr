"""Generic, service-agnostic differ."""

from __future__ import annotations

from typing import Any, Callable, Hashable

from configarr.diff.model import FieldDiff, Op, Plan, ResourcePlan


def _field_diffs(before: dict, after: dict) -> list[FieldDiff]:
    diffs: list[FieldDiff] = []
    # Only desired keys drive updates; absent desired keys are left to the
    # provider's build_desired (which already merged defaults/current).
    for key in after:
        if before.get(key) != after[key]:
            diffs.append(FieldDiff(path=key, before=before.get(key), after=after[key]))
    return diffs


def diff(
    kind: str,
    current: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    match_key: Callable[[dict], Hashable],
    normalize: Callable[[dict], dict],
) -> Plan:
    cur_by_key = {match_key(r): r for r in current}
    plans: list[ResourcePlan] = []
    for d in desired:
        key = match_key(d)
        nd = normalize(d)
        if key not in cur_by_key:
            plans.append(ResourcePlan(kind, key, Op.CREATE, _field_diffs({}, nd)))
            continue
        nc = normalize(cur_by_key[key])
        fds = _field_diffs(nc, nd)
        plans.append(ResourcePlan(kind, key, Op.UPDATE if fds else Op.UNCHANGED, fds))
    return Plan(resources=plans)
