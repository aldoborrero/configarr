import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.cleanuparr.sections import (
    CleanuparrArrSettingsProvider,
    CleanuparrSectionProvider,
)

CU = "http://cleanuparr.test"

QUEUE_CLEANER = {
    "enabled": False,
    "cronExpression": "0 0/5 * * * ?",
    "failedImport": {
        "maxStrikes": 0,
        "skipIfNotFoundInClient": True,
        "patternMode": "Include",
    },
    "ignoredDownloads": [],
}


def _section(config, path="queue_cleaner"):
    return CleanuparrSectionProvider(CU, "key", config, f"cleanuparr.{path}", path)


def _mock_get(path, payload):
    responses.get(f"{CU}/api/configuration/{path}", json=payload)


@responses.activate
def test_section_change_plans_dotted_update(plan_provider):
    _mock_get("queue_cleaner", QUEUE_CLEANER)
    plan = plan_provider(
        _section({"enabled": True, "failed_import": {"max_strikes": 3}})
    )
    [res] = plan.resources
    assert res.op is Op.UPDATE
    paths = {d.path for d in res.field_diffs}
    assert paths == {"enabled", "failedImport.maxStrikes"}


@responses.activate
def test_section_unchanged_is_noop(plan_provider):
    _mock_get("queue_cleaner", QUEUE_CLEANER)
    plan = plan_provider(
        _section({"enabled": False, "failed_import": {"pattern_mode": "include"}})
    )
    assert not plan.has_changes


@responses.activate
def test_section_put_carries_every_current_field(plan_provider, apply_changes):
    _mock_get("queue_cleaner", QUEUE_CLEANER)
    responses.put(f"{CU}/api/configuration/queue_cleaner", json={})
    provider = _section({"failed_import": {"max_strikes": 3}})
    apply_changes(provider, plan_provider(provider))
    body = json.loads(responses.calls[-1].request.body)
    # Full-replace PUT: untouched settings are sent back unchanged.
    assert body["cronExpression"] == "0 0/5 * * * ?"
    assert body["failedImport"] == {
        "maxStrikes": 3,
        "skipIfNotFoundInClient": True,
        "patternMode": "Include",
    }


@responses.activate
def test_section_without_config_does_nothing(plan_provider):
    plan = plan_provider(_section(None))
    assert plan.resources == []
    assert len(responses.calls) == 0


@responses.activate
def test_arr_settings_update_ignores_instances(plan_provider, apply_changes):
    _mock_get(
        "sonarr",
        {"id": "x", "type": "Sonarr", "failedImportMaxStrikes": -1, "instances": []},
    )
    responses.put(f"{CU}/api/configuration/sonarr", json={})
    provider = CleanuparrArrSettingsProvider(
        CU,
        "key",
        {"sonarr": {"failed_import_max_strikes": 3, "instances": {"S": {}}}},
        "cleanuparr.arr_settings",
    )
    plan = plan_provider(provider)
    [res] = plan.resources
    assert res.op is Op.UPDATE and res.key == "sonarr"
    apply_changes(provider, plan)
    assert json.loads(responses.calls[-1].request.body) == {"failedImportMaxStrikes": 3}


def test_arr_settings_rejects_unknown_arr_type():
    with pytest.raises(ValueError, match="unknown arr type"):
        CleanuparrArrSettingsProvider(
            CU, "key", {"sonar": {"failed_import_max_strikes": 1}}, "k"
        )
