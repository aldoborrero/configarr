import responses

from configarr.diff.model import Op
from configarr.diff.providers.download_clients import DownloadClientProvider

RADARR = "http://radarr.test"

# /downloadclient/schema entry for the configured implementation.
SCHEMA = [
    {
        "implementation": "Transmission",
        "configContract": "TransmissionSettings",
        "protocol": "torrent",
        "fields": [
            {"name": "host", "value": ""},
            {"name": "port", "value": 9091},
            {"name": "urlBase", "value": "/transmission/"},
        ],
    }
]

# A download client already on the instance, matched by name.
EXISTING = {
    "id": 1,
    "name": "Transmission",
    "implementation": "Transmission",
    "configContract": "TransmissionSettings",
    "protocol": "torrent",
    "enable": True,
    "priority": 1,
    "tags": [],
    "fields": [
        {"name": "host", "value": "localhost"},
        {"name": "port", "value": 9091},
        {"name": "urlBase", "value": "/transmission/"},
    ],
}

CONFIG = {
    "Transmission": {
        "implementation": "Transmission",
        "settings": {"host": "localhost", "port": 9091},
    }
}


def _radarr(config):
    return DownloadClientProvider(
        base_url=RADARR, api_key="k", config=config, kind="radarr.download_client"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[])
    responses.get(f"{RADARR}/api/v3/downloadclient/schema", json=SCHEMA)
    plan = plan_provider(_radarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Transmission"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_builds_fields_from_schema():
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[])
    responses.get(f"{RADARR}/api/v3/downloadclient/schema", json=SCHEMA)
    cfg = {
        "Transmission": {"implementation": "Transmission", "settings": {"host": "h"}}
    }
    [desired] = _radarr(cfg).build_desired()
    assert desired["implementation"] == "Transmission"
    assert desired["configContract"] == "TransmissionSettings"
    assert desired["protocol"] == "torrent"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured value overrides the schema default; unset fields keep the default.
    assert fields["host"] == "h"
    assert fields["port"] == 9091
    assert fields["urlBase"] == "/transmission/"
    assert "id" not in desired


@responses.activate
def test_updates_existing_by_name(plan_provider):
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[EXISTING])
    cfg = {
        "Transmission": {"implementation": "Transmission", "settings": {"port": 9092}}
    }
    plan = plan_provider(_radarr(cfg))
    assert [r.key for r in plan.resources] == ["Transmission"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_update_merges_over_current():
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[EXISTING])
    cfg = {
        "Transmission": {"implementation": "Transmission", "settings": {"port": 9092}}
    }
    [desired] = _radarr(cfg).build_desired()
    # Server-managed key carried over for the PUT.
    assert desired["id"] == 1
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured override applied; other current field values kept.
    assert fields["port"] == 9092
    assert fields["host"] == "localhost"
    assert fields["urlBase"] == "/transmission/"


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share a single GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{RADARR}/api/v3/downloadclient", json=[EXISTING])
    plan_provider(_radarr(CONFIG))
    assert current.call_count == 1


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[EXISTING])
    plan = plan_provider(_radarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[EXISTING])
    plan = plan_provider(_radarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_configured_secret_does_not_perpetually_diff(plan_provider):
    # apiKey/password come back masked, so a configured secret must be skipped from
    # the comparison or every plan would report a phantom UPDATE.
    existing = {
        **EXISTING,
        "name": "Sab",
        "implementation": "Sabnzbd",
        "fields": [
            {"name": "host", "value": "localhost", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[existing])
    cfg = {
        "Sab": {
            "implementation": "Sabnzbd",
            "settings": {"host": "localhost", "apiKey": "real-secret"},
        }
    }
    plan = plan_provider(_radarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_schema_privacy_secret_does_not_perpetually_diff(plan_provider):
    # A secret field NOT named apiKey/password: its schema *privacy* marks it secret,
    # so it must be skipped from the diff or a configured value would perpetually
    # UPDATE against the masked server value.
    existing = {
        **EXISTING,
        "name": "Bot",
        "implementation": "TelegramBot",
        "fields": [
            {"name": "host", "value": "localhost", "privacy": "normal"},
            {"name": "botToken", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[existing])
    cfg = {
        "Bot": {
            "implementation": "TelegramBot",
            "settings": {"host": "localhost", "botToken": "real-token"},
        }
    }
    plan = plan_provider(_radarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[])
    responses.get(f"{RADARR}/api/v3/downloadclient/schema", json=SCHEMA)
    created = {**EXISTING}
    responses.post(f"{RADARR}/api/v3/downloadclient", json=created)
    p = _radarr(CONFIG)
    apply_changes(p, plan_provider(p))
    # forceSave must be passed so the server skips the live connectivity test.
    assert any("forceSave=true" in c.request.url for c in responses.calls)

    responses.reset()
    responses.get(f"{RADARR}/api/v3/downloadclient", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
