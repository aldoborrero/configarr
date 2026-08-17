import pytest
import responses

from configarr.model import Op
from configarr.providers.prowlarr.applications import ApplicationProvider

PROWLARR = "http://prowlarr.test"

# /applications/schema entries, indexed by implementation.
SCHEMA = [
    {
        "name": "Sonarr",
        "implementation": "Sonarr",
        "configContract": "SonarrSettings",
        "fields": [
            {"name": "baseUrl", "value": ""},
            {"name": "prowlarrUrl", "value": "http://prowlarr"},
        ],
    },
    {
        "name": "Radarr",
        "implementation": "Radarr",
        "configContract": "RadarrSettings",
        "fields": [
            {"name": "baseUrl", "value": ""},
        ],
    },
]

# An application already on the instance, matched by name.
EXISTING = {
    "id": 1,
    "name": "Sonarr",
    "implementation": "Sonarr",
    "configContract": "SonarrSettings",
    "syncLevel": "fullSync",
    "tags": [],
    "fields": [
        {"name": "baseUrl", "value": "http://sonarr"},
        {"name": "prowlarrUrl", "value": "http://prowlarr"},
    ],
}

CONFIG = {
    "Sonarr": {
        "implementation": "Sonarr",
        "settings": {"baseUrl": "http://sonarr", "prowlarrUrl": "http://prowlarr"},
    }
}


def _prowlarr(config):
    return ApplicationProvider(
        base_url=PROWLARR, api_key="k", config=config, kind="prowlarr.application"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    plan = plan_provider(_prowlarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Sonarr"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_builds_fields_from_schema():
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    cfg = {"Sonarr": {"implementation": "Sonarr", "settings": {"baseUrl": "http://x"}}}
    [desired] = _prowlarr(cfg).build_desired()
    assert desired["implementation"] == "Sonarr"
    assert desired["configContract"] == "SonarrSettings"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured value overrides the schema default; unset fields keep the default.
    assert fields["baseUrl"] == "http://x"
    assert fields["prowlarrUrl"] == "http://prowlarr"
    # Application default sync level.
    assert desired["syncLevel"] == "fullSync"
    assert "id" not in desired


@responses.activate
def test_create_uses_configured_sync_level():
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "sync_level": "addOnly",
            "settings": {},
        }
    }
    [desired] = _prowlarr(cfg).build_desired()
    assert desired["syncLevel"] == "addOnly"


@responses.activate
def test_invalid_sync_level_raises():
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "sync_level": "bogus",
            "settings": {},
        }
    }
    with pytest.raises(ValueError):
        _prowlarr(cfg).build_desired()


@responses.activate
def test_updates_existing_by_name(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/applications", json=[EXISTING])
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "settings": {"baseUrl": "http://sonarr2"},
        }
    }
    plan = plan_provider(_prowlarr(cfg))
    assert [r.key for r in plan.resources] == ["Sonarr"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_update_merges_over_current():
    responses.get(f"{PROWLARR}/api/v1/applications", json=[EXISTING])
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "settings": {"baseUrl": "http://sonarr2"},
        }
    }
    [desired] = _prowlarr(cfg).build_desired()
    # Server-managed key carried over for the PUT.
    assert desired["id"] == 1
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured override applied; other current field values kept.
    assert fields["baseUrl"] == "http://sonarr2"
    assert fields["prowlarrUrl"] == "http://prowlarr"


@responses.activate
def test_missing_implementation_raises(plan_provider):
    # Omitting `implementation` on a new application would send None to the server
    # (opaque 422); validate locally with a message naming the resource.
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    cfg = {"NoImpl": {"settings": {"baseUrl": "http://sonarr"}}}
    with pytest.raises(ValueError, match="application: NoImpl"):
        _prowlarr(cfg).build_desired()


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/applications", json=[EXISTING])
    plan = plan_provider(_prowlarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/applications", json=[EXISTING])
    plan = plan_provider(_prowlarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_normalize_drops_secret_before_build_desired():
    # normalize() must drop secrets even if called before build_desired() populates
    # the secret-name set — the set has to be self-enforcing, not order-dependent.
    existing = {
        **EXISTING,
        "fields": [
            {"name": "baseUrl", "value": "http://sonarr"},
            {"name": "prowlarrUrl", "value": "http://prowlarr"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{PROWLARR}/api/v1/applications", json=[existing])
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "settings": {
                "baseUrl": "http://sonarr",
                "prowlarrUrl": "http://prowlarr",
                "apiKey": "real-secret",
            },
        }
    }
    p = _prowlarr(cfg)
    desired_like = {
        "fields": [
            {"name": "baseUrl", "value": "http://sonarr"},
            {"name": "prowlarrUrl", "value": "http://prowlarr"},
            {"name": "apiKey", "value": "real-secret"},
        ],
    }
    assert "apiKey" not in p.normalize(desired_like)["fields"]


@responses.activate
def test_configured_secret_does_not_perpetually_diff(plan_provider):
    # Secrets (apiKey/password) come back masked, so a configured secret must be
    # skipped from the comparison or every plan would report a phantom UPDATE.
    existing = {
        **EXISTING,
        "fields": [
            {"name": "baseUrl", "value": "http://sonarr"},
            {"name": "prowlarrUrl", "value": "http://prowlarr"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{PROWLARR}/api/v1/applications", json=[existing])
    cfg = {
        "Sonarr": {
            "implementation": "Sonarr",
            "settings": {
                "baseUrl": "http://sonarr",
                "prowlarrUrl": "http://prowlarr",
                "apiKey": "real-secret",
            },
        }
    }
    plan = plan_provider(_prowlarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{PROWLARR}/api/v1/applications", json=[])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    created = {**EXISTING}
    responses.post(f"{PROWLARR}/api/v1/applications", json=created)
    p = _prowlarr(CONFIG)
    apply_changes(p, plan_provider(p))
    # forceSave must be passed so the server skips the live connectivity test.
    assert any("forceSave=true" in c.request.url for c in responses.calls)

    responses.reset()
    responses.get(f"{PROWLARR}/api/v1/applications", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{PROWLARR}/api/v1/applications", json=[EXISTING])
    responses.get(f"{PROWLARR}/api/v1/applications/schema", json=SCHEMA)
    plan_provider(_prowlarr(CONFIG))
    assert current.call_count == 1
