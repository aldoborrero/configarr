import responses
from responses import matchers

from configarr.model import Op
from configarr.providers.sabnzbd.categories import SabnzbdCategoryProvider

SAB = "http://sab.test"

# A category already present on the instance. SABnzbd returns a server-managed
# `order` key the provider does not manage.
CURRENT_CATEGORY = {
    "name": "movies",
    "order": 1,
    "pp": "3",
    "script": "None",
    "dir": "movies",
    "newzbin": "",
    "priority": -100,
}

CONFIG = {
    "movies": {
        "pp": "3",
        "script": "None",
        "dir": "movies",
        "priority": -100,
    }
}


def _provider(config):
    return SabnzbdCategoryProvider(
        base_url=SAB, api_key="k", config=config, kind="sabnzbd.category"
    )


def _mock_get_config(categories):
    responses.get(
        f"{SAB}/api",
        json={"config": {"categories": categories}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )


def _mock_set_config():
    responses.get(
        f"{SAB}/api",
        json={"config": {"categories": []}},
        match=[
            matchers.query_param_matcher({"mode": "set_config"}, strict_match=False)
        ],
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    _mock_get_config([])
    plan = plan_provider(_provider(CONFIG))
    assert [r.key for r in plan.resources] == ["movies"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_applies_documented_defaults():
    _mock_get_config([])
    cfg = {"movies": {"dir": "movies"}}
    [desired] = _provider(cfg).build_desired()
    assert desired["name"] == "movies"
    assert desired["dir"] == "movies"
    # Documented defaults for keys the user did not set.
    assert desired["pp"] == ""
    assert desired["script"] == "None"
    assert desired["newzbin"] == ""
    assert desired["priority"] == -100


@responses.activate
def test_update_changes_only_set_field(plan_provider):
    _mock_get_config([CURRENT_CATEGORY])
    cfg = {"movies": {"priority": 0}}
    plan = plan_provider(_provider(cfg))
    assert plan.resources[0].op is Op.UPDATE
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "priority" in paths
    assert "script" not in paths


@responses.activate
def test_update_keeps_unset_fields_at_server_value():
    _mock_get_config([CURRENT_CATEGORY])
    cfg = {"movies": {"priority": 0}}
    [desired] = _provider(cfg).build_desired()
    # Unset fields carry the current server value rather than a default.
    assert desired["dir"] == "movies"
    assert desired["pp"] == "3"
    assert desired["priority"] == 0


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get_config([CURRENT_CATEGORY])
    plan = plan_provider(_provider({}))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    _mock_get_config([CURRENT_CATEGORY])
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get_config([])
    _mock_set_config()
    p = _provider(CONFIG)
    apply_changes(p, plan_provider(p))
    assert any("mode=set_config" in c.request.url for c in responses.calls)

    responses.reset()
    # After apply the category reflects the desired object (defaults + overrides).
    _mock_get_config([CURRENT_CATEGORY])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(
        f"{SAB}/api",
        json={"config": {"categories": [CURRENT_CATEGORY]}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )
    plan_provider(_provider(CONFIG))
    assert current.call_count == 1
