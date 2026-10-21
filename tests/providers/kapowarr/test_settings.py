import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.kapowarr.common import MASK, KapowarrError
from configarr.providers.kapowarr.settings import KapowarrSettingsProvider

KP = "http://kapowarr.test"
SETTINGS = f"{KP}/api/settings"

CURRENT = {
    "api_key": "the-key",
    "auth_password": MASK,
    "proxy_password": "",
    "comicvine_api_key": "cv-old",
    "flaresolverr_base_url": "",
    "download_folder": "/downloads/",
    "url_base": "",
    "rename_downloaded_files": True,
    "volume_padding": 2,
    "format_preference": [],
}


def _provider(config):
    return KapowarrSettingsProvider(KP, "the-key", config, "kapowarr.settings")


def _get(payload=CURRENT):
    responses.get(SETTINGS, json={"error": None, "result": payload})


@responses.activate
def test_requests_carry_api_key_param(plan_provider):
    _get()
    plan_provider(_provider({"volume_padding": 2}))
    assert responses.calls[0].request.params == {"api_key": "the-key"}


@responses.activate
def test_unchanged_settings_in_kapowarr_spelling_are_noop(plan_provider):
    _get({**CURRENT, "flaresolverr_base_url": "http://fs:8191"})
    plan = plan_provider(
        _provider(
            {
                "download_folder": "/downloads",
                "flaresolverr_base_url": "http://fs:8191/",
                "comicvine_api_key": "cv-old",
                "auth_password": "hunter2",  # masked server-side: never diffed
            }
        )
    )
    assert not plan.has_changes


@responses.activate
def test_partial_put_sends_only_changed_and_masked_keys(plan_provider, apply_changes):
    _get()
    responses.put(SETTINGS, json={"error": None, "result": CURRENT})
    provider = _provider(
        {
            "comicvine_api_key": "cv-new",
            "flaresolverr_base_url": "http://fs:8191",
            "rename_downloaded_files": True,
            "auth_password": "hunter2",
        }
    )
    plan = plan_provider(provider)
    [res] = plan.resources
    assert res.op is Op.UPDATE
    assert {d.path for d in res.field_diffs} == {
        "comicvine_api_key",
        "flaresolverr_base_url",
    }
    # The secret never enters the plan in clear text.
    cv = next(d for d in res.field_diffs if d.path == "comicvine_api_key")
    assert "cv-new" not in str(cv.after) and "cv-old" not in str(cv.before)

    apply_changes(provider, plan)
    body = json.loads(responses.calls[-1].request.body)
    assert body == {
        "comicvine_api_key": "cv-new",
        "flaresolverr_base_url": "http://fs:8191",
        "auth_password": "hunter2",
    }


@responses.activate
def test_unknown_setting_is_ignored(plan_provider, caplog):
    _get()
    plan = plan_provider(_provider({"no_such_setting": 1}))
    assert not plan.has_changes
    assert "no_such_setting" in caplog.text


def test_api_key_setting_is_rejected():
    with pytest.raises(ValueError, match="api_key"):
        _provider({"api_key": "x"})


def test_empty_config_makes_no_requests(plan_provider):
    # responses not activated: any HTTP call would hit the network and fail.
    assert not plan_provider(_provider(None)).resources


@responses.activate
def test_error_hides_the_key(plan_provider):
    responses.get(SETTINGS, json={"error": "ApiKeyInvalid", "result": {}}, status=401)
    with pytest.raises(KapowarrError) as exc:
        plan_provider(_provider({"volume_padding": 3}))
    assert "ApiKeyInvalid" in str(exc.value)
    assert "the-key" not in str(exc.value)
