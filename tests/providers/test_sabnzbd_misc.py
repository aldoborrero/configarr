import responses
from responses import matchers

from configarr.diff.model import Op
from configarr.diff.providers.sabnzbd_misc import SabnzbdMiscProvider

SAB = "http://sab.test"

# The misc section SABnzbd returns: many keys, only the allow-listed ones managed.
# Bools are echoed as 0/1 ints. SABnzbd also returns keys the provider does not
# manage (e.g. `api_key`), which must stay out of the diff.
CURRENT_MISC = {
    "download_dir": "/incomplete",
    "complete_dir": "/complete",
    "bandwidth_max": "100M",
    "cache_limit": "1G",
    "pause_on_post_processing": 0,
    "pre_check": 0,
    "api_key": "unmanaged-secret",
}

CONFIG = {
    "download_dir": "/incomplete",
    "complete_dir": "/complete",
    "bandwidth_max": "100M",
    "cache_limit": "1G",
}


def _provider(config):
    return SabnzbdMiscProvider(
        base_url=SAB, api_key="k", config=config, kind="sabnzbd.misc"
    )


def _mock_get_config(misc):
    responses.get(
        f"{SAB}/api",
        json={"config": {"misc": misc}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )


def _mock_set_config():
    responses.get(
        f"{SAB}/api",
        json={"config": {"misc": {}}},
        match=[
            matchers.query_param_matcher({"mode": "set_config"}, strict_match=False)
        ],
    )


@responses.activate
def test_singleton_plans_as_update(plan_provider):
    _mock_get_config(CURRENT_MISC)
    cfg = {"bandwidth_max": "50M"}
    plan = plan_provider(_provider(cfg))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_bool_encoded_as_one_zero():
    _mock_get_config(CURRENT_MISC)
    cfg = {"pause_on_post_processing": True, "pre_check": False}
    [desired] = _provider(cfg).build_desired()
    assert desired["pause_on_post_processing"] == 1
    assert desired["pre_check"] == 0


@responses.activate
def test_update_changes_only_set_field(plan_provider):
    _mock_get_config(CURRENT_MISC)
    cfg = {"bandwidth_max": "50M"}
    plan = plan_provider(_provider(cfg))
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "bandwidth_max" in paths
    assert "complete_dir" not in paths


@responses.activate
def test_update_keeps_unset_fields_at_server_value():
    _mock_get_config(CURRENT_MISC)
    cfg = {"bandwidth_max": "50M"}
    [desired] = _provider(cfg).build_desired()
    assert desired["bandwidth_max"] == "50M"
    # Unset managed fields carry the current server value.
    assert desired["complete_dir"] == "/complete"
    assert desired["download_dir"] == "/incomplete"


@responses.activate
def test_unmanaged_server_keys_stay_out_of_diff(plan_provider):
    _mock_get_config(CURRENT_MISC)
    # CONFIG sets only managed keys to their current value, so a re-plan is a
    # no-op even though the server returns the unmanaged api_key.
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get_config(CURRENT_MISC)
    plan = plan_provider(_provider({}))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    _mock_get_config(CURRENT_MISC)
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_sets_misc_per_keyword(plan_provider, apply_changes):
    _mock_get_config(CURRENT_MISC)
    _mock_set_config()
    cfg = {"bandwidth_max": "50M"}
    p = _provider(cfg)
    apply_changes(p, plan_provider(p))
    set_calls = [c for c in responses.calls if "mode=set_config" in c.request.url]
    assert set_calls
    # misc is written per keyword/value, not as a name=... object.
    assert any("keyword=bandwidth_max" in c.request.url for c in set_calls)
    assert all("section=misc" in c.request.url for c in set_calls)


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get_config(CURRENT_MISC)
    _mock_set_config()
    cfg = {"bandwidth_max": "50M"}
    p = _provider(cfg)
    apply_changes(p, plan_provider(p))

    responses.reset()
    applied = dict(CURRENT_MISC)
    applied["bandwidth_max"] = "50M"
    _mock_get_config(applied)
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(
        f"{SAB}/api",
        json={"config": {"misc": CURRENT_MISC}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )
    plan_provider(_provider(CONFIG))
    assert current.call_count == 1
