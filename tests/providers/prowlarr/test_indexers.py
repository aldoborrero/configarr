import pytest
import responses

from configarr.plan import Op
from configarr.providers.prowlarr.indexers import IndexerProvider

PROWLARR = "http://prowlarr.test"

# /indexer/schema entries. Generic implementations (Newznab) resolve by
# implementation; Cardigann sites share implementation="Cardigann" and resolve by
# schema name via the `definition` config key.
SCHEMA = [
    {
        "name": "Newznab",
        "implementation": "Newznab",
        "configContract": "NewznabSettings",
        "protocol": "usenet",
        "fields": [
            {"name": "baseUrl", "value": ""},
            {"name": "apiPath", "value": "/api"},
        ],
    },
    {
        "name": "Nyaa.si",
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "protocol": "torrent",
        "fields": [
            {"name": "definitionFile", "value": "nyaasi"},
        ],
    },
]

# An indexer already on the instance, matched by name.
EXISTING = {
    "id": 1,
    "name": "Newznab",
    "implementation": "Newznab",
    "configContract": "NewznabSettings",
    "protocol": "usenet",
    "enable": True,
    "priority": 25,
    "appProfileId": 1,
    "redirect": False,
    "tags": [],
    "fields": [
        {"name": "baseUrl", "value": "http://news"},
        {"name": "apiPath", "value": "/api"},
    ],
}

CONFIG = {
    "Newznab": {
        "implementation": "Newznab",
        "settings": {"baseUrl": "http://news", "apiPath": "/api"},
    }
}


def _prowlarr(config):
    return IndexerProvider(
        base_url=PROWLARR, api_key="k", config=config, kind="prowlarr.indexer"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    plan = plan_provider(_prowlarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Newznab"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_builds_fields_from_schema():
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    cfg = {
        "Newznab": {"implementation": "Newznab", "settings": {"baseUrl": "http://x"}}
    }
    [desired] = _prowlarr(cfg).build_desired()
    assert desired["implementation"] == "Newznab"
    assert desired["configContract"] == "NewznabSettings"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured value overrides the schema default; unset fields keep the default.
    assert fields["baseUrl"] == "http://x"
    assert fields["apiPath"] == "/api"
    # Indexer-only defaults.
    assert desired["appProfileId"] == 1
    assert desired["redirect"] is False
    assert desired["priority"] == 25
    assert "id" not in desired


@responses.activate
def test_create_resolves_cardigann_schema_by_definition():
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    cfg = {
        "Nyaa": {
            "implementation": "Cardigann",
            "definition": "Nyaa.si",
            "settings": {},
        }
    }
    [desired] = _prowlarr(cfg).build_desired()
    # Cardigann shares one implementation; the definition selects the site schema.
    assert desired["configContract"] == "CardigannSettings"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    assert fields["definitionFile"] == "nyaasi"


@responses.activate
def test_updates_existing_by_name(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[EXISTING])
    cfg = {
        "Newznab": {
            "implementation": "Newznab",
            "settings": {"baseUrl": "http://news2"},
        }
    }
    plan = plan_provider(_prowlarr(cfg))
    assert [r.key for r in plan.resources] == ["Newznab"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_update_merges_over_current():
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[EXISTING])
    cfg = {
        "Newznab": {
            "implementation": "Newznab",
            "settings": {"baseUrl": "http://news2"},
        }
    }
    [desired] = _prowlarr(cfg).build_desired()
    # Server-managed key carried over for the PUT.
    assert desired["id"] == 1
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    # Configured override applied; other current field values kept.
    assert fields["baseUrl"] == "http://news2"
    assert fields["apiPath"] == "/api"


@responses.activate
def test_missing_implementation_raises(plan_provider):
    # Omitting `implementation` on a new indexer would send None to the server
    # (opaque 422); validate locally with a message naming the resource.
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    cfg = {"NoImpl": {"settings": {"baseUrl": "http://news"}}}
    with pytest.raises(ValueError, match="indexer: NoImpl"):
        _prowlarr(cfg).build_desired()


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[EXISTING])
    plan = plan_provider(_prowlarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[EXISTING])
    plan = plan_provider(_prowlarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_normalize_drops_secret_before_build_desired():
    # normalize() must drop secrets even if called before build_desired() populates
    # the secret-name set — the set has to be self-enforcing, not order-dependent.
    existing = {
        **EXISTING,
        "fields": [
            {"name": "baseUrl", "value": "http://news", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[existing])
    cfg = {
        "Newznab": {
            "implementation": "Newznab",
            "settings": {"baseUrl": "http://news", "apiKey": "real-secret"},
        }
    }
    p = _prowlarr(cfg)
    desired_like = {
        "fields": [
            {"name": "baseUrl", "value": "http://news"},
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
            {"name": "baseUrl", "value": "http://news", "privacy": "normal"},
            {"name": "apiKey", "value": "********", "privacy": "apiKey"},
        ],
    }
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[existing])
    cfg = {
        "Newznab": {
            "implementation": "Newznab",
            "settings": {"baseUrl": "http://news", "apiKey": "real-secret"},
        }
    }
    plan = plan_provider(_prowlarr(cfg))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    created = {**EXISTING}
    responses.post(f"{PROWLARR}/api/v1/indexer", json=created)
    p = _prowlarr(CONFIG)
    apply_changes(p, plan_provider(p))
    # forceSave must be passed so the server skips the live connectivity test.
    assert any("forceSave=true" in c.request.url for c in responses.calls)

    responses.reset()
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{PROWLARR}/api/v1/indexer", json=[EXISTING])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    plan_provider(_prowlarr(CONFIG))
    assert current.call_count == 1


@responses.activate
@responses.activate
def test_unknown_cardigann_definition_raises():
    responses.get(f"{PROWLARR}/api/v1/indexer", json=[])
    responses.get(f"{PROWLARR}/api/v1/indexer/schema", json=SCHEMA)
    cfg = {"MySite": {"implementation": "Cardigann", "definition": "NoSuchSite"}}
    with pytest.raises(ValueError, match="unknown Prowlarr indexer definition"):
        _prowlarr(cfg).build_desired()
