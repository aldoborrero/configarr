import pytest
import responses
from responses import matchers

from configarr.diff.model import Op
from configarr.diff.providers.sabnzbd_servers import SabnzbdServerProvider

SAB = "http://sab.test"

# A news server already present on the instance. SABnzbd echoes bools as 1/0 ints
# and never returns the real password (here shown masked).
CURRENT_SERVER = {
    "name": "news",
    "host": "news.example.com",
    "port": 563,
    "ssl": 1,
    "ssl_verify": 2,
    "ssl_ciphers": "",
    "username": "user",
    "password": "****",
    "connections": 8,
    "priority": 0,
    "retention": 0,
    "timeout": 60,
    "enable": 1,
    "required": 0,
    "optional": 0,
    "send_group": 0,
    "notes": "",
}

CONFIG = {
    "news": {
        "host": "news.example.com",
        "username": "user",
        "password": "secret",
        "connections": 8,
    }
}


def _provider(config):
    return SabnzbdServerProvider(
        base_url=SAB, api_key="k", config=config, kind="sabnzbd.server"
    )


def _mock_get_config(servers):
    responses.get(
        f"{SAB}/api",
        json={"config": {"servers": servers}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )


def _mock_set_config():
    responses.get(
        f"{SAB}/api",
        json={"config": {"servers": []}},
        match=[
            matchers.query_param_matcher({"mode": "set_config"}, strict_match=False)
        ],
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    _mock_get_config([])
    plan = plan_provider(_provider(CONFIG))
    assert [r.key for r in plan.resources] == ["news"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_applies_documented_defaults():
    _mock_get_config([])
    [desired] = _provider(CONFIG).build_desired()
    assert desired["name"] == "news"
    assert desired["host"] == "news.example.com"
    assert desired["username"] == "user"
    assert desired["connections"] == 8
    # Documented defaults for keys the user did not set.
    assert desired["port"] == 563
    assert desired["ssl"] == 1
    assert desired["enable"] == 1
    assert desired["timeout"] == 60


@responses.activate
def test_bools_encoded_as_one_or_zero():
    _mock_get_config([CURRENT_SERVER])
    cfg = {"news": {"host": "news.example.com", "ssl": False}}
    [desired] = _provider(cfg).build_desired()
    assert desired["ssl"] == 0


@responses.activate
def test_update_changes_only_set_field(plan_provider):
    _mock_get_config([CURRENT_SERVER])
    cfg = {"news": {"host": "news.example.com", "connections": 20}}
    plan = plan_provider(_provider(cfg))
    assert plan.resources[0].op is Op.UPDATE
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "connections" in paths
    assert "timeout" not in paths


@responses.activate
def test_update_keeps_unset_fields_at_server_value():
    _mock_get_config([CURRENT_SERVER])
    cfg = {"news": {"host": "news.example.com", "connections": 20}}
    [desired] = _provider(cfg).build_desired()
    # Unset fields carry the current server value rather than a default.
    assert desired["timeout"] == 60
    assert desired["ssl"] == 1
    assert desired["connections"] == 20


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get_config([CURRENT_SERVER])
    plan = plan_provider(_provider({}))
    assert not plan.resources


@responses.activate
def test_missing_host_raises():
    _mock_get_config([])
    with pytest.raises(ValueError, match="host"):
        _provider({"news": {"username": "user"}}).build_desired()


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    _mock_get_config([CURRENT_SERVER])
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_configured_secret_does_not_perpetually_diff(plan_provider):
    # Config sets a real password; the server only ever returns it masked. The
    # secret must be skipped from the diff so an unchanged server stays UNCHANGED.
    _mock_get_config([CURRENT_SERVER])
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
    # After apply the server reflects the desired object (defaults + overrides).
    created = {**CURRENT_SERVER}
    _mock_get_config([created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(
        f"{SAB}/api",
        json={"config": {"servers": [CURRENT_SERVER]}},
        match=[
            matchers.query_param_matcher({"mode": "get_config"}, strict_match=False)
        ],
    )
    plan_provider(_provider(CONFIG))
    assert current.call_count == 1
