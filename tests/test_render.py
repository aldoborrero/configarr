from configarr.model import FieldDiff, Op, Plan, ResourcePlan
from configarr.render import plan_resources_json, render_plan


def _update_plan(diffs):
    return Plan(
        resources=[
            ResourcePlan(
                "bazarr.provider",
                "opensubtitlescom",
                Op.UPDATE,
                [FieldDiff(path=p, before=b, after=a) for p, b, a in diffs],
            )
        ]
    )


def test_secret_named_fields_are_redacted_in_json():
    plan = _update_plan([("password", "old", "new"), ("username", "a", "b")])
    [res] = plan_resources_json(plan)
    by_path = {d["path"]: d for d in res["field_diffs"]}
    assert by_path["password"]["before"] == "***"
    assert by_path["password"]["after"] == "***"
    # Non-secret fields pass through unchanged.
    assert by_path["username"]["after"] == "b"


def test_secret_named_fields_are_redacted_in_text():
    text = render_plan(_update_plan([("apikey", "s3cr3t", "rotated")]))
    assert "s3cr3t" not in text
    assert "rotated" not in text
    assert "***" in text
