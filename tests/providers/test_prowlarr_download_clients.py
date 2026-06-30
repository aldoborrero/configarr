import responses

from configarr.diff.model import Op
from configarr.diff.providers.prowlarr_download_clients import (
    ProwlarrDownloadClientProvider,
)

PROWLARR = "http://prowlarr.test"

# /downloadclient/schema entry for the configured implementation. A None default
# (urlBase) must be substituted so Prowlarr does not NullReference on a null field.
SCHEMA = [
    {
        "implementation": "Transmission",
        "configContract": "TransmissionSettings",
        "protocol": "torrent",
        "fields": [
            {"name": "host", "value": ""},
            {"name": "port", "value": 9091},
            {"name": "urlBase", "value": None},
        ],
    }
]

# A download client already on the instance, matched by name (case-insensitively).
EXISTING = {
    "id": 1,
    "name": "Transmission",
    "implementation": "Transmission",
    "configContract": "TransmissionSettings",
    "protocol": "torrent",
    "enable": True,
    "priority": 1,
    "tags": [],
    "categories": [],
    "fields": [
        {"name": "host", "value": "localhost"},
        {"name": "port", "value": 9091},
        {"name": "urlBase", "value": ""},
    ],
}

CONFIG = {
    "Transmission": {
        "implementation": "Transmission",
        "settings": {"host": "localhost", "port": 9091},
    }
}


def _prowlarr(config):
    return ProwlarrDownloadClientProvider(
        base_url=PROWLARR, api_key="k", config=config, kind="prowlarr.download_client"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[])
    responses.get(f"{PROWLARR}/api/v1/downloadclient/schema", json=SCHEMA)
    plan = plan_provider(_prowlarr(CONFIG))
    # Identity (and thus the plan key) is the case-folded name.
    assert [r.key for r in plan.resources] == ["transmission"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_substitutes_none_field_default_and_hardcodes_categories():
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[])
    responses.get(f"{PROWLARR}/api/v1/downloadclient/schema", json=SCHEMA)
    cfg = {
        "Transmission": {"implementation": "Transmission", "settings": {"host": "h"}}
    }
    [desired] = _prowlarr(cfg).build_desired()
    assert desired["configContract"] == "TransmissionSettings"
    assert desired["protocol"] == "torrent"
    assert desired["categories"] == []
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    assert fields["host"] == "h"
    assert fields["port"] == 9091
    # A None schema default (and an unset setting) becomes "" — never None.
    assert fields["urlBase"] == ""
    assert "id" not in desired


@responses.activate
def test_matches_existing_case_insensitively(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[EXISTING])
    cfg = {
        "transmission": {"implementation": "Transmission", "settings": {"port": 9092}}
    }
    plan = plan_provider(_prowlarr(cfg))
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_update_merges_over_current():
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[EXISTING])
    cfg = {
        "Transmission": {"implementation": "Transmission", "settings": {"port": 9092}}
    }
    [desired] = _prowlarr(cfg).build_desired()
    assert desired["id"] == 1
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    assert fields["port"] == 9092
    assert fields["host"] == "localhost"


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[EXISTING])
    plan = plan_provider(_prowlarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[EXISTING])
    plan = plan_provider(_prowlarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_configured_secret_does_not_perpetually_diff(plan_provider):
    existing = {
        **EXISTING,
        "name": "Sab",
        "implementation": "Sabnzbd",
        "fields": [
            {"name": "host", "value": "localhost", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[existing])
    cfg = {
        "Sab": {
            "implementation": "Sabnzbd",
            "settings": {"host": "localhost", "apiKey": "real-secret"},
        }
    }
    plan = plan_provider(_prowlarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[])
    responses.get(f"{PROWLARR}/api/v1/downloadclient/schema", json=SCHEMA)
    created = {**EXISTING}
    responses.post(f"{PROWLARR}/api/v1/downloadclient", json=created)
    p = _prowlarr(CONFIG)
    apply_changes(p, plan_provider(p))
    # forceSave must be passed so the server skips the live connectivity test.
    assert any("forceSave=true" in c.request.url for c in responses.calls)

    responses.reset()
    responses.get(f"{PROWLARR}/api/v1/downloadclient", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
