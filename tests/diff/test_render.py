from configarr.diff.model import FieldDiff, Op, Plan, ResourcePlan
from configarr.diff.render import render_plan


def test_render_shows_changes():
    plan = Plan(
        [
            ResourcePlan(
                "radarr.custom_format", "x265", Op.UPDATE, [FieldDiff("score", 0, 100)]
            )
        ]
    )
    out = render_plan(plan)
    assert "x265" in out and "score" in out and "100" in out


def test_render_empty_plan():
    plan = Plan([ResourcePlan("radarr.custom_format", "x265", Op.UNCHANGED, [])])
    assert render_plan(plan) == "No changes."
