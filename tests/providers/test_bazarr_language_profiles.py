import json

import responses

from configarr.model import Op
from configarr.providers.bazarr_language_profiles import (
    BazarrLanguageProfileProvider,
)

BAZARR = "http://bazarr.test"

# Languages Bazarr reports as available; resolution falls back to this API for
# names not in the static map.
LANGUAGES = [
    {"name": "English", "code2": "en", "code3": "eng"},
    {"name": "Spanish", "code2": "es", "code3": "spa"},
    {"name": "Klingon", "code2": "tlh", "code3": "tlh"},
]

# A profile the server already stores, in the shape Bazarr actually returns — note
# every item carries audio_only_include, a key the config never sets. The built
# profile must emit it too, or the full-replace list swap drops it and the profile
# diffs forever.
DEFAULT_PROFILE = {
    "profileId": 1,
    "name": "Default",
    "items": [
        {
            "id": 1,
            "language": "en",
            "audio_exclude": "False",
            "hi": "False",
            "forced": "False",
            "audio_only_include": "False",
        },
        {
            "id": 2,
            "language": "es",
            "audio_exclude": "False",
            "hi": "False",
            "forced": "False",
            "audio_only_include": "False",
        },
    ],
    "cutoff": 1,
    "mustContain": [],
    "mustNotContain": [],
    "originalFormat": None,
}

# A profile only on the server, absent from any config — must be preserved.
SERVER_ONLY_PROFILE = {
    "profileId": 9,
    "name": "ServerOnly",
    "items": [
        {
            "id": 1,
            "language": "fr",
            "audio_exclude": "False",
            "hi": "False",
            "forced": "False",
            "audio_only_include": "False",
        }
    ],
    "cutoff": 1,
    "mustContain": [],
    "mustNotContain": [],
    "originalFormat": None,
}

CONFIG_DEFAULT = {
    "name": "Default",
    "languages": ["english", "spanish"],
    "cutoff": "english",
}


def _provider(config):
    return BazarrLanguageProfileProvider(
        base_url=BAZARR,
        api_key="k",
        config=config,
        kind="bazarr.language_profile",
    )


def _mock_get(profiles, languages=LANGUAGES):
    responses.get(f"{BAZARR}/api/system/languages/profiles", json=profiles)
    responses.get(f"{BAZARR}/api/system/languages", json=languages)


def _mock_post():
    responses.post(f"{BAZARR}/api/system/settings", json={})


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    plan = plan_provider(_provider([]))
    assert not plan.resources


@responses.activate
def test_matching_profile_is_noop(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    plan = plan_provider(_provider([CONFIG_DEFAULT]))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_new_profile_plans_create(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    plan = plan_provider(
        _provider([{"name": "New", "languages": ["english"], "cutoff": "english"}])
    )
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.CREATE
    assert plan.resources[0].key == "New"


@responses.activate
def test_changed_language_plans_update(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    plan = plan_provider(
        _provider([{"name": "Default", "languages": ["english"], "cutoff": "english"}])
    )
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_unknown_language_is_dropped(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    p = _provider(
        [{"name": "New", "languages": ["english", "nonsense"], "cutoff": "english"}]
    )
    built = p.build_desired()[0]
    codes = [item["language"] for item in built["items"]]
    assert codes == ["en"]


@responses.activate
def test_cutoff_resolves_to_listed_language_item_id(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    p = _provider(
        [{"name": "New", "languages": ["english", "spanish"], "cutoff": "spanish"}]
    )
    built = p.build_desired()[0]
    # Spanish is the second listed language → item id 2.
    assert built["cutoff"] == 2


@responses.activate
def test_cutoff_not_listed_is_none(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    p = _provider([{"name": "New", "languages": ["english"], "cutoff": "spanish"}])
    built = p.build_desired()[0]
    assert built["cutoff"] is None


@responses.activate
def test_language_resolved_via_api_fallback(plan_provider):
    # Klingon is not in the static map; resolution must consult /api/system/languages.
    _mock_get([DEFAULT_PROFILE])
    p = _provider([{"name": "New", "languages": ["klingon"], "cutoff": "klingon"}])
    built = p.build_desired()[0]
    assert [item["language"] for item in built["items"]] == ["tlh"]


@responses.activate
def test_apply_posts_full_list_preserving_server_only(plan_provider, apply_changes):
    _mock_get([DEFAULT_PROFILE, SERVER_ONLY_PROFILE])
    _mock_post()
    p = _provider([{"name": "Default", "languages": ["english"], "cutoff": "english"}])
    apply_changes(p, plan_provider(p))
    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert post_calls
    body = post_calls[-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    # The form field carries the whole profiles list as JSON.
    assert "languages-profiles" in rendered
    # ServerOnly is preserved alongside the rewritten Default.
    assert "ServerOnly" in rendered
    assert "Default" in rendered


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get([DEFAULT_PROFILE, SERVER_ONLY_PROFILE])
    _mock_post()
    p = _provider([{"name": "Default", "languages": ["english"], "cutoff": "english"}])
    apply_changes(p, plan_provider(p))

    # The server now stores the rewritten Default (english only) plus ServerOnly.
    applied_default = {
        "profileId": 1,
        "name": "Default",
        "items": [
            {
                "id": 1,
                "language": "en",
                "audio_exclude": "False",
                "hi": "False",
                "forced": "False",
                "audio_only_include": "False",
            }
        ],
        "cutoff": 1,
        "mustContain": [],
        "mustNotContain": [],
        "originalFormat": None,
    }
    responses.reset()
    _mock_get([applied_default, SERVER_ONLY_PROFILE])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_dict_language_carries_flags(plan_provider):
    _mock_get([DEFAULT_PROFILE])
    p = _provider(
        [
            {
                "name": "New",
                "languages": [
                    {
                        "name": "english",
                        "hi": True,
                        "forced": True,
                        "audio_only_include": True,
                    }
                ],
                "cutoff": "english",
            }
        ]
    )
    built = p.build_desired()[0]
    item = built["items"][0]
    assert item["language"] == "en"
    assert item["hi"] == "True"
    assert item["forced"] == "True"
    assert item["audio_only_include"] == "True"


@responses.activate
def test_apply_payload_is_valid_json(plan_provider, apply_changes):
    _mock_get([DEFAULT_PROFILE])
    _mock_post()
    p = _provider([{"name": "Default", "languages": ["english"], "cutoff": "english"}])
    apply_changes(p, plan_provider(p))
    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    body = post_calls[-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    # Extract the JSON blob from the multipart body and confirm it parses to a list.
    start = rendered.index("[")
    end = rendered.rindex("]") + 1
    parsed = json.loads(rendered[start:end])
    assert isinstance(parsed, list)


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(
        f"{BAZARR}/api/system/languages/profiles", json=[DEFAULT_PROFILE]
    )
    responses.get(f"{BAZARR}/api/system/languages", json=LANGUAGES)
    plan_provider(_provider([CONFIG_DEFAULT]))
    assert current.call_count == 1
