import responses

from configarr.model import Op
from configarr.providers.quality_profiles import QualityProfileProvider

BASE = "http://radarr.test"

# /qualityprofile/schema: a default profile listing every quality (in semantic
# order, all disallowed) and one FormatItem per existing custom format (score 0).
SCHEMA = {
    "name": "",
    "upgradeAllowed": False,
    "cutoff": 1,
    "items": [
        {"quality": {"id": 1, "name": "SDTV"}, "items": [], "allowed": False},
        {"quality": {"id": 2, "name": "WEBDL-1080p"}, "items": [], "allowed": False},
        {"quality": {"id": 3, "name": "Bluray-1080p"}, "items": [], "allowed": False},
    ],
    "minFormatScore": 0,
    "cutoffFormatScore": 0,
    "minUpgradeFormatScore": 1,
    "formatItems": [
        {"format": 10, "name": "x265", "score": 0},
        {"format": 11, "name": "HDR", "score": 0},
    ],
    "language": {"id": 1, "name": "Any"},
}

CONFIG = [
    {
        "name": "HD",
        "upgrade": {
            "allowed": True,
            "until_quality": "Bluray-1080p",
            "until_score": 10000,
        },
        "min_format_score": 0,
        "custom_format_scores": {"x265": 100},
        "quality_sort": "top",
        "qualities": [{"name": "WEBDL-1080p"}, {"name": "Bluray-1080p"}],
        "language": None,
    }
]

# What the instance returns once the "HD" profile exists (build_desired echoed
# back with a server-assigned id). Items are in config/priority order — enabled
# first (WEBDL, Bluray), unwanted appended disabled (SDTV).
EXISTING = {
    "id": 5,
    "name": "HD",
    "upgradeAllowed": True,
    "cutoff": 3,
    "items": [
        {"quality": {"id": 2, "name": "WEBDL-1080p"}, "items": [], "allowed": True},
        {"quality": {"id": 3, "name": "Bluray-1080p"}, "items": [], "allowed": True},
        {"quality": {"id": 1, "name": "SDTV"}, "items": [], "allowed": False},
    ],
    "minFormatScore": 0,
    "cutoffFormatScore": 10000,
    "minUpgradeFormatScore": 1,
    "formatItems": [
        {"format": 10, "name": "x265", "score": 100},
        {"format": 11, "name": "HDR", "score": 0},
    ],
    "language": {"id": 1, "name": "Any"},
}


# GET /api/v3/language: Radarr's language list (negative ids for the synthetic
# "Any"/"Original" entries, positive for real languages).
LANGUAGES = [
    {"id": -1, "name": "Any"},
    {"id": -2, "name": "Original"},
    {"id": 1, "name": "English"},
]


def _provider(config, kind="radarr.quality_profile"):
    return QualityProfileProvider(base_url=BASE, api_key="k", config=config, kind=kind)


@responses.activate
def test_language_resolved_in_desired():
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    responses.get(f"{BASE}/api/v3/language", json=LANGUAGES)
    config = [{**CONFIG[0], "language": "Original"}]
    [desired] = _provider(config).build_desired()
    assert desired["language"] == {"id": -2, "name": "Original"}


@responses.activate
def test_language_unknown_leaves_profile_language_untouched():
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    responses.get(f"{BASE}/api/v3/language", json=LANGUAGES)
    config = [{**CONFIG[0], "language": "Klingon"}]
    [desired] = _provider(config).build_desired()
    # Unresolved name falls back to the schema/current language (Any).
    assert desired["language"] == {"id": 1, "name": "Any"}


@responses.activate
def test_language_ignored_for_sonarr():
    # Sonarr quality profiles carry no language filter; the /language endpoint
    # must never be hit even when config supplies a language key.
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    config = [{**CONFIG[0], "language": "Original"}]
    [desired] = _provider(config, kind="sonarr.quality_profile").build_desired()
    assert desired["language"] == {"id": 1, "name": "Any"}


@responses.activate
def test_create_when_absent(plan_provider):
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    plan = plan_provider(_provider(CONFIG))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_cutoff_and_scores_resolved_in_desired():
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    [desired] = _provider(CONFIG).build_desired()
    assert desired["cutoff"] == 3  # Bluray-1080p resolved by name -> id
    allowed = {i["quality"]["name"] for i in desired["items"] if i["allowed"]}
    assert allowed == {"WEBDL-1080p", "Bluray-1080p"}
    scores = {fi["name"]: fi["score"] for fi in desired["formatItems"]}
    assert scores == {"x265": 100, "HDR": 0}  # every CF present (validator)


@responses.activate
def test_items_in_config_priority_order():
    # qualities order drives priority: enabled first (config order), then the
    # unwanted quality (SDTV) appended disabled.
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    [desired] = _provider(CONFIG).build_desired()
    order = [i["quality"]["name"] for i in desired["items"]]
    assert order == ["WEBDL-1080p", "Bluray-1080p", "SDTV"]


@responses.activate
def test_custom_group_created_from_config():
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    config = [
        {
            **CONFIG[0],
            "qualities": [
                {"name": "1080p", "qualities": ["WEBDL-1080p", "Bluray-1080p"]}
            ],
            "upgrade": {**CONFIG[0]["upgrade"], "until_quality": "1080p"},
        }
    ]
    [desired] = _provider(config).build_desired()
    group = desired["items"][0]
    assert group["name"] == "1080p"
    assert group["allowed"] is True
    assert group["id"] == 1001  # new group id (max(1000, ...) + 1)
    assert [c["quality"]["name"] for c in group["items"]] == [
        "WEBDL-1080p",
        "Bluray-1080p",
    ]
    # SDTV falls through disabled at the bottom; cutoff resolves to the group id.
    assert desired["items"][-1]["quality"]["name"] == "SDTV"
    assert desired["cutoff"] == 1001


@responses.activate
def test_custom_group_is_idempotent(plan_provider):
    # Once the grouped profile exists on the server, a re-plan is a no-op: the
    # group id is reused from current.
    existing = {
        "id": 5,
        "name": "HD",
        "upgradeAllowed": True,
        "cutoff": 1001,
        "items": [
            {
                "id": 1001,
                "name": "1080p",
                "allowed": True,
                "items": [
                    {"quality": {"id": 2, "name": "WEBDL-1080p"}, "allowed": True},
                    {"quality": {"id": 3, "name": "Bluray-1080p"}, "allowed": True},
                ],
            },
            {"quality": {"id": 1, "name": "SDTV"}, "items": [], "allowed": False},
        ],
        "minFormatScore": 0,
        "cutoffFormatScore": 10000,
        "minUpgradeFormatScore": 1,
        "formatItems": [
            {"format": 10, "name": "x265", "score": 100},
            {"format": 11, "name": "HDR", "score": 0},
        ],
        "language": {"id": 1, "name": "Any"},
    }
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[existing])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    config = [
        {
            **CONFIG[0],
            "qualities": [
                {"name": "1080p", "qualities": ["WEBDL-1080p", "Bluray-1080p"]}
            ],
            "upgrade": {**CONFIG[0]["upgrade"], "until_quality": "1080p"},
        }
    ]
    plan = plan_provider(_provider(config))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_custom_group_build_is_self_consistent(plan_provider):
    # Strongest offline idempotency proof: build once against the empty server
    # (source = schema, flat), have Radarr "echo back" exactly what we PUT, then a
    # fresh plan against that echo (source = current, grouped) must be a no-op.
    config = [
        {
            **CONFIG[0],
            "qualities": [
                {"name": "1080p", "qualities": ["WEBDL-1080p", "Bluray-1080p"]}
            ],
            "upgrade": {**CONFIG[0]["upgrade"], "until_quality": "1080p"},
        }
    ]
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    [built] = _provider(config).build_desired()

    # Radarr stores exactly what it received, assigning a profile id.
    server_profile = {**built, "id": 7}
    responses.reset()
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[server_profile])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    plan = plan_provider(_provider(config))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_idempotent_when_current_equals_desired(plan_provider):
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[EXISTING])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    responses.post(f"{BASE}/api/v3/qualityprofile", json=EXISTING, status=201)
    p = _provider(CONFIG)
    apply_changes(p, plan_provider(p))

    # Second run: instance now returns the created profile. Schema is cached from
    # the first run, so do NOT re-register it (would leave an unfired mock).
    responses.reset()
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[EXISTING])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{BASE}/api/v3/qualityprofile", json=[EXISTING])
    responses.get(f"{BASE}/api/v3/qualityprofile/schema", json=SCHEMA)
    responses.get(f"{BASE}/api/v3/language", json=LANGUAGES)
    plan_provider(_provider(CONFIG))
    assert current.call_count == 1
