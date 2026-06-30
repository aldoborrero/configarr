import pytest
import responses

from configarr.diff.model import Op
from configarr.diff.providers.notifications import NotificationProvider

RADARR = "http://radarr.test"
SONARR = "http://sonarr.test"

# /notification/schema entry for the configured implementation.
SCHEMA = [
    {
        "implementation": "Webhook",
        "configContract": "WebhookSettings",
        "fields": [
            {"name": "url", "value": ""},
            {"name": "method", "value": 1},
        ],
    }
]

# A notification already on the instance, matched by name.
EXISTING = {
    "id": 1,
    "name": "Webhook",
    "implementation": "Webhook",
    "configContract": "WebhookSettings",
    "onDownload": True,
    "onUpgrade": True,
    "onRename": True,
    "tags": [],
    "fields": [
        {"name": "url", "value": "http://hook"},
        {"name": "method", "value": 1},
    ],
}

CONFIG = {
    "Webhook": {
        "implementation": "Webhook",
        "settings": {"url": "http://hook", "method": 1},
    }
}


def _radarr(config):
    return NotificationProvider(
        base_url=RADARR, api_key="k", config=config, kind="radarr.notification"
    )


def _sonarr(config):
    return NotificationProvider(
        base_url=SONARR, api_key="k", config=config, kind="sonarr.notification"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{RADARR}/api/v3/notification", json=[])
    responses.get(f"{RADARR}/api/v3/notification/schema", json=SCHEMA)
    plan = plan_provider(_radarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Webhook"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_builds_fields_from_schema():
    responses.get(f"{RADARR}/api/v3/notification", json=[])
    responses.get(f"{RADARR}/api/v3/notification/schema", json=SCHEMA)
    cfg = {"Webhook": {"implementation": "Webhook", "settings": {"url": "http://x"}}}
    [desired] = _radarr(cfg).build_desired()
    assert desired["implementation"] == "Webhook"
    assert desired["configContract"] == "WebhookSettings"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured value overrides the schema default; unset fields keep the default.
    assert fields["url"] == "http://x"
    assert fields["method"] == 1
    # Event flags default to True.
    assert desired["onDownload"] is True
    assert desired["onUpgrade"] is True
    assert desired["onRename"] is True
    assert "id" not in desired


@responses.activate
def test_radarr_omits_on_import_complete():
    responses.get(f"{RADARR}/api/v3/notification", json=[])
    responses.get(f"{RADARR}/api/v3/notification/schema", json=SCHEMA)
    [desired] = _radarr(CONFIG).build_desired()
    # Radarr never reads onImportComplete.
    assert "onImportComplete" not in desired


@responses.activate
def test_sonarr_includes_on_import_complete():
    responses.get(f"{SONARR}/api/v3/notification", json=[])
    responses.get(f"{SONARR}/api/v3/notification/schema", json=SCHEMA)
    [desired] = _sonarr(CONFIG).build_desired()
    assert desired["onImportComplete"] is True


@responses.activate
def test_updates_existing_by_name(plan_provider):
    responses.get(f"{RADARR}/api/v3/notification", json=[EXISTING])
    cfg = {
        "Webhook": {
            "implementation": "Webhook",
            "settings": {"url": "http://hook2"},
        }
    }
    plan = plan_provider(_radarr(cfg))
    assert [r.key for r in plan.resources] == ["Webhook"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_update_merges_over_current():
    responses.get(f"{RADARR}/api/v3/notification", json=[EXISTING])
    cfg = {
        "Webhook": {"implementation": "Webhook", "settings": {"url": "http://hook2"}}
    }
    [desired] = _radarr(cfg).build_desired()
    # Server-managed key carried over for the PUT.
    assert desired["id"] == 1
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured override applied; other current field values kept.
    assert fields["url"] == "http://hook2"
    assert fields["method"] == 1


@responses.activate
def test_missing_implementation_raises(plan_provider):
    # Omitting `implementation` on a new notification would send None to the server
    # (opaque 422); validate locally with a message naming the resource.
    responses.get(f"{RADARR}/api/v3/notification", json=[])
    cfg = {"NoImpl": {"settings": {"url": "http://hook"}}}
    with pytest.raises(ValueError, match="notification: NoImpl"):
        _radarr(cfg).build_desired()


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{RADARR}/api/v3/notification", json=[EXISTING])
    plan = plan_provider(_radarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{RADARR}/api/v3/notification", json=[EXISTING])
    plan = plan_provider(_radarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_normalize_drops_secret_before_build_desired():
    # normalize() must drop secrets even if called before build_desired() populates
    # the secret-name set — the set has to be self-enforcing, not order-dependent.
    existing = {
        **EXISTING,
        "name": "Telegram",
        "implementation": "Telegram",
        "fields": [
            {"name": "chatId", "value": "123", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{RADARR}/api/v3/notification", json=[existing])
    cfg = {
        "Telegram": {
            "implementation": "Telegram",
            "settings": {"chatId": "123", "apiKey": "real-secret"},
        }
    }
    p = _radarr(cfg)
    desired_like = {
        "implementation": "Telegram",
        "fields": [
            {"name": "chatId", "value": "123"},
            {"name": "apiKey", "value": "real-secret"},
        ],
    }
    assert "apiKey" not in p.normalize(desired_like)["fields"]


@responses.activate
def test_configured_secret_does_not_perpetually_diff(plan_provider):
    # Secrets (apiKey/token) come back masked, so a configured secret must be
    # skipped from the comparison or every plan would report a phantom UPDATE.
    existing = {
        **EXISTING,
        "name": "Telegram",
        "implementation": "Telegram",
        "fields": [
            {"name": "chatId", "value": "123", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{RADARR}/api/v3/notification", json=[existing])
    cfg = {
        "Telegram": {
            "implementation": "Telegram",
            "settings": {"chatId": "123", "apiKey": "real-secret"},
        }
    }
    plan = plan_provider(_radarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{RADARR}/api/v3/notification", json=[])
    responses.get(f"{RADARR}/api/v3/notification/schema", json=SCHEMA)
    created = {**EXISTING}
    responses.post(f"{RADARR}/api/v3/notification", json=created)
    p = _radarr(CONFIG)
    apply_changes(p, plan_provider(p))
    # forceSave must be passed so the server skips the live connectivity test.
    assert any("forceSave=true" in c.request.url for c in responses.calls)

    responses.reset()
    responses.get(f"{RADARR}/api/v3/notification", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{RADARR}/api/v3/notification", json=[EXISTING])
    responses.get(f"{RADARR}/api/v3/notification/schema", json=SCHEMA)
    plan_provider(_radarr(CONFIG))
    assert current.call_count == 1
