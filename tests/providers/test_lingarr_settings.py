import pytest
import responses

from configarr.model import Op
from configarr.providers.lingarr_settings import LingarrSettingsProvider

LIN = "http://lingarr.test"

# Lingarr returns every setting as a string, including bools ("true") and ints.
CURRENT = {
    "service_type": "libretranslate",
    "local_ai_model": "old-model",
    "local_ai_api_key": "REALKEY-abc123",
    "use_batch_translation": "false",
    "max_batch_size": "10",
}


def _provider(config, kind="lingarr.translation"):
    return LingarrSettingsProvider(base_url=LIN, api_key="", config=config, kind=kind)


def _mock_get(payload, status=200):
    responses.post(
        f"{LIN}/api/setting/multiple/get",
        json=payload,
        status=status,
    )


@responses.activate
def test_changed_setting_plans_as_update(plan_provider):
    _mock_get(CURRENT)
    plan = plan_provider(_provider({"local_ai_model": "deepseek/deepseek-v4-flash"}))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_unchanged_setting_is_noop(plan_provider):
    _mock_get(CURRENT)
    # Same value, and bool/int written as YAML native — coerce_scalar makes them equal.
    plan = plan_provider(
        _provider({"use_batch_translation": False, "max_batch_size": 10})
    )
    assert not plan.has_changes


@responses.activate
def test_bool_and_int_encoded_as_strings():
    _mock_get(CURRENT)
    [desired] = _provider(
        {"use_batch_translation": True, "max_batch_size": 300}
    ).build_desired()
    assert desired["use_batch_translation"] == "true"
    assert desired["max_batch_size"] == "300"


@responses.activate
def test_unknown_key_warns_and_is_dropped(caplog):
    _mock_get(CURRENT)
    # sonarr_url belongs to the integration group, not translation.
    cfg = {"local_ai_model": "m", "sonarr_url": "http://s"}
    with caplog.at_level("WARNING"):
        [desired] = _provider(cfg).build_desired()
    assert "sonarr_url" not in desired
    assert any(
        "sonarr_url" in r.getMessage() and "translation" in r.getMessage()
        for r in caplog.records
    )


@responses.activate
def test_secret_value_stays_out_of_the_plan(plan_provider):
    _mock_get(CURRENT)
    # A changed key must diff, but the cleartext must never appear in the plan.
    plan = plan_provider(_provider({"local_ai_api_key": "NEWKEY-xyz789"}))
    rendered = str(plan.resources)
    assert "NEWKEY-xyz789" not in rendered
    assert "REALKEY-abc123" not in rendered


@responses.activate
def test_onboarding_403_raises_a_clear_error():
    # The 403 surfaces when the diff reads current state (fetch_current), not when
    # build_desired emits the declared keys.
    _mock_get({}, status=403)
    with pytest.raises(RuntimeError, match="onboarding"):
        _provider({"local_ai_model": "m"}).fetch_current()


@responses.activate
def test_apply_posts_the_payload_to_set():
    _mock_get(CURRENT)
    set_call = responses.post(f"{LIN}/api/setting/multiple/set", json={})
    prov = _provider({"local_ai_model": "deepseek/deepseek-v4-flash"})
    from configarr.model import ResourcePlan
    from configarr.providers.base import Action

    action = prov.to_action(
        ResourcePlan("lingarr.translation", "settings", Op.UPDATE, []),
        None,
        {"local_ai_model": "deepseek/deepseek-v4-flash"},
    )
    assert isinstance(action, Action)
    prov.apply(action)
    assert set_call.call_count == 1


@responses.activate
def test_integration_group_manages_arr_keys():
    _mock_get({"sonarr_url": "", "sonarr_api_key": ""})
    [desired] = _provider(
        {"sonarr_url": "http://sonarr:8989", "sonarr_api_key": "k"},
        kind="lingarr.integration",
    ).build_desired()
    assert desired == {"sonarr_url": "http://sonarr:8989", "sonarr_api_key": "k"}
