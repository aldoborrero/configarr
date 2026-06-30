import pytest

from configarr.engine import diff
from configarr.model import Op


def _norm(r):  # identity normalize for the test
    return r


def test_diff_detects_create_update_unchanged():
    current = [{"name": "a", "v": 1}, {"name": "b", "v": 1}]
    desired = [{"name": "a", "v": 1}, {"name": "b", "v": 2}, {"name": "c", "v": 9}]
    plan = diff("cf", current, desired, match_key=lambda r: r["name"], normalize=_norm)
    by_key = {r.key: r for r in plan.resources}
    assert by_key["a"].op is Op.UNCHANGED
    assert by_key["b"].op is Op.UPDATE
    assert [(d.path, d.before, d.after) for d in by_key["b"].field_diffs] == [
        ("v", 1, 2)
    ]
    assert by_key["c"].op is Op.CREATE


def test_diff_is_idempotent_on_equal_inputs():
    current = [{"name": "a", "v": 1}]
    desired = [{"name": "a", "v": 1}]  # different objects, equal values
    plan = diff("cf", current, desired, match_key=lambda r: r["name"], normalize=_norm)
    assert not plan.has_changes


def test_diff_rejects_duplicate_keys():
    # A duplicate identity on the server side is a hard error, not a silent
    # last-write-wins. The message names the side and the offending key.
    dup = [{"name": "a", "v": 1}, {"name": "a", "v": 2}]
    with pytest.raises(ValueError, match=r"duplicate key in current: 'a'"):
        diff("cf", dup, [], match_key=lambda r: r["name"], normalize=_norm)


def test_diff_rejects_duplicate_keys_in_desired():
    # The realistic user-error path: two config entries collapse to the same
    # match_key (e.g. two custom formats named "a", or two delay profiles with
    # the same tag-set). The engine must refuse rather than let the second entry
    # silently shadow the first; the message names the desired side and the key.
    dup = [{"name": "a", "v": 1}, {"name": "a", "v": 2}]
    with pytest.raises(ValueError, match=r"duplicate key in desired: 'a'"):
        diff("cf", [], dup, match_key=lambda r: r["name"], normalize=_norm)


def test_default_diff_ignores_current_only_keys():
    # Schema-overlay/additive mode (the CF pilot default): a key present only in
    # current is not surfaced, because apply only touches desired keys.
    current = [{"name": "a", "v": 1, "server_managed": 7}]
    desired = [{"name": "a", "v": 1}]
    plan = diff("cf", current, desired, match_key=lambda r: r["name"], normalize=_norm)
    assert plan.resources[0].op is Op.UNCHANGED


def test_full_replace_surfaces_current_only_keys():
    # Full-replace apply PUTs the whole desired object, so a key present only in
    # current would be reset on the server. The plan must report UPDATE (not
    # UNCHANGED) and surface the key so it can't under-report.
    current = [{"name": "a", "v": 1, "server_managed": 7}]
    desired = [{"name": "a", "v": 1}]
    plan = diff(
        "qp",
        current,
        desired,
        match_key=lambda r: r["name"],
        normalize=_norm,
        full_replace=True,
    )
    r = plan.resources[0]
    assert r.op is Op.UPDATE
    surfaced = {d.path: (d.before, d.after) for d in r.field_diffs}
    assert surfaced["server_managed"] == (7, None)


def test_prune_emits_delete_for_current_only_keys():
    # With prune enabled, a resource present in current but absent from desired is
    # an unmanaged leftover the engine should flag for deletion.
    current = [{"name": "a", "v": 1}, {"name": "stale", "v": 9}]
    desired = [{"name": "a", "v": 1}]
    plan = diff(
        "cf",
        current,
        desired,
        match_key=lambda r: r["name"],
        normalize=_norm,
        prune=True,
    )
    by_key = {r.key: r for r in plan.resources}
    assert by_key["a"].op is Op.UNCHANGED
    assert by_key["stale"].op is Op.DELETE


def test_prune_off_leaves_current_only_keys_alone():
    # Default additive behavior: an unmanaged resource is never deleted.
    current = [{"name": "a", "v": 1}, {"name": "stale", "v": 9}]
    desired = [{"name": "a", "v": 1}]
    plan = diff("cf", current, desired, match_key=lambda r: r["name"], normalize=_norm)
    assert {r.key for r in plan.resources} == {"a"}


def test_full_replace_is_unchanged_when_desired_covers_current():
    # When build_desired merged over current, desired carries every current key,
    # so the guard adds nothing and the plan stays UNCHANGED.
    current = [{"name": "a", "v": 1, "server_managed": 7}]
    desired = [{"name": "a", "v": 1, "server_managed": 7}]
    plan = diff(
        "qp",
        current,
        desired,
        match_key=lambda r: r["name"],
        normalize=_norm,
        full_replace=True,
    )
    assert plan.resources[0].op is Op.UNCHANGED
