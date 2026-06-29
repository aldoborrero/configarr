import pytest

from configarr.diff.engine import diff
from configarr.diff.model import Op


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
    dup = [{"name": "a", "v": 1}, {"name": "a", "v": 2}]
    with pytest.raises(ValueError):
        diff("cf", dup, [], match_key=lambda r: r["name"], normalize=_norm)
