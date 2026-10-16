import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.lingarr.onboarding import LingarrOnboardingProvider
from configarr.providers.lingarr.settings import LingarrSettingsProvider

LIN = "http://lingarr.test"


def _onboarding(config):
    return LingarrOnboardingProvider(LIN, "", config, "lingarr.onboarding")


def _status(requires):
    responses.get(
        f"{LIN}/api/auth/authenticated",
        json={"authenticated": not requires, "requiresOnboarding": requires},
    )


@responses.activate
def test_fresh_instance_plans_and_applies_onboarding(plan_provider, apply_changes):
    _status(True)
    responses.post(f"{LIN}/api/auth/onboarding", json={})
    provider = _onboarding({"enable_user_auth": False})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(provider, plan)
    post = next(c for c in responses.calls if c.request.method == "POST")
    assert json.loads(post.request.body) == {"enableUserAuth": "false"}


@responses.activate
def test_onboarded_instance_is_noop(plan_provider):
    _status(False)
    assert not plan_provider(_onboarding({})).has_changes


@responses.activate
def test_already_onboarded_race_409_is_accepted(plan_provider, apply_changes):
    _status(True)
    responses.post(f"{LIN}/api/auth/onboarding", status=409, json={})
    provider = _onboarding({})
    apply_changes(provider, plan_provider(provider))  # does not raise


@responses.activate
def test_unmanaged_onboarding_makes_no_call(plan_provider):
    assert plan_provider(_onboarding(None)).resources == []
    assert len(responses.calls) == 0


@responses.activate
def test_settings_403_is_empty_when_onboarding_is_managed(plan_provider):
    responses.post(f"{LIN}/api/setting/multiple/get", status=403, json={})
    provider = LingarrSettingsProvider(
        LIN, "", {"max_batch_size": 150}, "lingarr.translation", onboarding_managed=True
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]


@responses.activate
def test_settings_403_still_errors_without_onboarding():
    responses.post(f"{LIN}/api/setting/multiple/get", status=403, json={})
    provider = LingarrSettingsProvider(
        LIN, "", {"max_batch_size": 150}, "lingarr.translation"
    )
    with pytest.raises(RuntimeError, match="onboarding"):
        provider.fetch_current()


@responses.activate
def test_api_key_is_sent_as_x_api_key():
    responses.post(f"{LIN}/api/setting/multiple/get", json={"max_batch_size": "1"})
    LingarrSettingsProvider(
        LIN, "secret", {"max_batch_size": 1}, "lingarr.translation"
    ).fetch_current()
    assert responses.calls[0].request.headers["X-Api-Key"] == "secret"


@responses.activate
def test_validation_group_manages_its_keys(plan_provider):
    responses.post(
        f"{LIN}/api/setting/multiple/get",
        json={"subtitle_validation_enabled": "false"},
    )
    provider = LingarrSettingsProvider(
        LIN,
        "",
        {"subtitle_validation_enabled": True, "ai_prompt": "nope"},
        "lingarr.validation",
    )
    [desired] = provider.build_desired()
    assert desired == {"subtitle_validation_enabled": "true"}
