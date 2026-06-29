"""Tests for the shared provider-test harness in tests/conftest.py.

These fixtures are the single source of truth every provider test reuses, so the
plan helper must mirror the runner's diff invocation (including full_replace) and
the apply helper must drive to_action/apply for changed resources.
"""

from configarr.diff.model import Op
from configarr.diff.providers.base import Action


class _FakeProvider:
    """Minimal in-memory provider: no HTTP, name-keyed, optional full_replace."""

    kind = "fake.resource"

    def __init__(self, current, desired, full_replace=False):
        self._current = current
        self._desired = desired
        self.full_replace = full_replace
        self.applied: list[Action] = []

    def match_key(self, resource):
        return resource["name"]

    def fetch_current(self):
        return self._current

    def build_desired(self):
        return self._desired

    def normalize(self, resource):
        return {k: v for k, v in resource.items() if k != "name"}

    def to_action(self, plan, current, desired):
        payload = dict(desired or {})
        if current is not None:
            payload["id"] = current["id"]
        return Action(op=plan.op, key=plan.key, payload=payload)

    def apply(self, action):
        self.applied.append(action)


def test_plan_provider_reports_create_for_desired_only(plan_provider):
    p = _FakeProvider(current=[], desired=[{"name": "a", "x": 1}])

    plan = plan_provider(p)

    assert [r.op for r in plan.resources] == [Op.CREATE]


def test_plan_provider_honors_full_replace_current_only_keys(plan_provider):
    # Desired drops a current-only key; full_replace must surface it as an UPDATE.
    p = _FakeProvider(
        current=[{"name": "a", "x": 1, "server_managed": True}],
        desired=[{"name": "a", "x": 1}],
        full_replace=True,
    )

    plan = plan_provider(p)

    assert plan.has_changes
    assert plan.resources[0].op is Op.UPDATE


def test_apply_changes_drives_apply_for_changed_resources(plan_provider, apply_changes):
    p = _FakeProvider(
        current=[{"id": 7, "name": "a", "x": 1}],
        desired=[{"name": "a", "x": 2}, {"name": "b", "x": 9}],
    )

    apply_changes(p, plan_provider(p))

    ops = {a.op for a in p.applied}
    assert ops == {Op.CREATE, Op.UPDATE}
    update = next(a for a in p.applied if a.op is Op.UPDATE)
    assert update.payload["id"] == 7  # current id threaded through for updates
