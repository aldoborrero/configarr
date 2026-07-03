from configarr.model import FieldDiff, Op, Plan, ResourcePlan


def test_resourceplan_is_changed():
    unchanged = ResourcePlan(kind="cf", key="x", op=Op.UNCHANGED, field_diffs=[])
    created = ResourcePlan(kind="cf", key="y", op=Op.CREATE, field_diffs=[])
    deleted = ResourcePlan(kind="cf", key="z", op=Op.DELETE, field_diffs=[])
    assert not unchanged.changed
    assert created.changed
    assert deleted.changed


def test_plan_summary_counts():
    plan = Plan(
        resources=[
            ResourcePlan("cf", "a", Op.CREATE, []),
            ResourcePlan("cf", "b", Op.UPDATE, [FieldDiff("score", 0, 100)]),
            ResourcePlan("cf", "c", Op.UNCHANGED, []),
        ]
    )
    assert plan.summary() == {Op.CREATE: 1, Op.UPDATE: 1, Op.UNCHANGED: 1}
    assert plan.has_changes
