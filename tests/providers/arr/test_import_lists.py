import responses

from configarr.plan import Op
from configarr.providers.arr.import_lists import ImportListProvider

BASE = "http://radarr.test"

SCHEMA = [
    {
        "implementation": "TraktPopularImport",
        "configContract": "TraktPopularSettings",
        "fields": [
            {"name": "traktListType", "value": 0},
            {"name": "apiKey", "value": ""},
        ],
    }
]

EXISTING = {
    "id": 1,
    "name": "Trakt",
    "implementation": "TraktPopularImport",
    "configContract": "TraktPopularSettings",
    "enabled": True,
    "enableAuto": True,
    "qualityProfileId": 1,
    "rootFolderPath": "/movies",
    "monitor": "movieOnly",
    "tags": [],
    "fields": [
        {"name": "traktListType", "value": 0},
        {"name": "apiKey", "value": "********", "privacy": "apiKey"},
    ],
}

CONFIG = {
    "Trakt": {
        "implementation": "TraktPopularImport",
        "enabled": True,
        "enableAuto": True,
        "qualityProfileId": 1,
        "rootFolderPath": "/movies",
        "monitor": "movieOnly",
        "settings": {"traktListType": 0},
    }
}


def _radarr(config):
    return ImportListProvider(
        base_url=BASE, api_key="k", config=config, kind="radarr.import_list"
    )


def _reads(lists):
    responses.get(f"{BASE}/api/v3/importlist", json=lists)
    responses.get(f"{BASE}/api/v3/importlist/schema", json=SCHEMA)


def test_is_prunable():
    assert ImportListProvider.prunable is True


@responses.activate
def test_creates_when_absent(plan_provider):
    _reads([])
    plan = plan_provider(_radarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Trakt"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_create_carries_top_level_and_schema_fields():
    _reads([])
    [desired] = _radarr(CONFIG).build_desired()
    # Top-level API fields pass straight through.
    assert desired["qualityProfileId"] == 1
    assert desired["rootFolderPath"] == "/movies"
    assert desired["monitor"] == "movieOnly"
    assert desired["configContract"] == "TraktPopularSettings"
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    assert fields["traktListType"] == 0


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    _reads([EXISTING])
    plan = plan_provider(_radarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_update_when_top_level_changes(plan_provider):
    _reads([EXISTING])
    cfg = {"Trakt": {**CONFIG["Trakt"], "monitor": "none"}}
    plan = plan_provider(_radarr(cfg))
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _reads([])
    responses.post(f"{BASE}/api/v3/importlist", json={**EXISTING}, status=201)
    p = _radarr(CONFIG)
    apply_changes(p, plan_provider(p))
    responses.reset()
    _reads([EXISTING])
    assert not plan_provider(_radarr(CONFIG)).has_changes


@responses.activate
def test_sonarr_only_fields_do_not_spurious_diff(plan_provider):
    # A Sonarr import list carries sonarr-only top fields; the radarr-only fields
    # are simply absent, so the superset normalize never invents a diff.
    sonarr_existing = {
        "id": 1,
        "name": "IMDb",
        "implementation": "ImdbListImport",
        "configContract": "ImdbListSettings",
        "enableAutomaticAdd": True,
        "seasonFolder": True,
        "seriesType": "standard",
        "shouldMonitor": "all",
        "qualityProfileId": 1,
        "rootFolderPath": "/tv",
        "tags": [],
        "fields": [{"name": "listId", "value": "ls123"}],
    }
    schema = [
        {
            "implementation": "ImdbListImport",
            "configContract": "ImdbListSettings",
            "fields": [{"name": "listId", "value": ""}],
        }
    ]
    responses.get(f"{BASE}/api/v3/importlist", json=[sonarr_existing])
    responses.get(f"{BASE}/api/v3/importlist/schema", json=schema)
    cfg = {
        "IMDb": {
            "implementation": "ImdbListImport",
            "enableAutomaticAdd": True,
            "seasonFolder": True,
            "seriesType": "standard",
            "shouldMonitor": "all",
            "qualityProfileId": 1,
            "rootFolderPath": "/tv",
            "settings": {"listId": "ls123"},
        }
    }
    p = ImportListProvider(
        base_url=BASE, api_key="k", config=cfg, kind="sonarr.import_list"
    )
    assert not plan_provider(p).has_changes, plan_provider(p).resources
