from configarr.model import FieldDiff, Op, Plan, ResourcePlan
from configarr.render import plan_resources_json, render_plan


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


def _secret_plan() -> Plan:
    # Bazarr returns provider passwords in clear text, so a real value can reach the
    # diff. The renderer must never print it, whatever the provider did upstream.
    return Plan(
        [
            ResourcePlan(
                "bazarr.provider",
                "opensubtitlescom",
                Op.UPDATE,
                [
                    FieldDiff("password", "s3cr3t-old", "s3cr3t-new"),
                    FieldDiff("username", "alice", "bob"),
                ],
            )
        ]
    )


def test_render_redacts_secret_field_values():
    out = render_plan(_secret_plan())
    assert "s3cr3t-old" not in out
    assert "s3cr3t-new" not in out
    assert "***" in out
    # Non-secret fields are still shown verbatim.
    assert "bob" in out


def test_json_redacts_secret_field_values():
    resources = plan_resources_json(_secret_plan())
    diffs = {d["path"]: d for d in resources[0]["field_diffs"]}
    assert diffs["password"]["before"] == "***"
    assert diffs["password"]["after"] == "***"
    assert diffs["username"]["after"] == "bob"
    assert "s3cr3t" not in str(resources)


def test_json_redacts_secret_on_create():
    # CREATE diffs carry before=None, after=<value>; a created secret must not leak.
    plan = Plan(
        [
            ResourcePlan(
                "radarr.download_client",
                "sab",
                Op.CREATE,
                [FieldDiff("apiKey", None, "top-secret-key")],
            )
        ]
    )
    resources = plan_resources_json(plan)
    assert resources[0]["field_diffs"][0]["after"] == "***"
    assert "top-secret-key" not in str(resources)
