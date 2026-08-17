import responses

from configarr.plan import Op
from configarr.providers.arr.delay_profiles import DelayProfileProvider

RADARR = "http://radarr.test"
SONARR = "http://sonarr.test"

# The built-in catch-all profile every instance ships with: empty tags, max order.
RADARR_DEFAULT = {
    "id": 1,
    "enableUsenet": True,
    "enableTorrent": True,
    "preferredProtocol": "usenet",
    "usenetDelay": 0,
    "torrentDelay": 0,
    "bypassIfHighestQuality": False,
    "bypassIfAboveCustomFormatScore": False,
    "minimumCustomFormatScore": 0,
    "order": 2147483647,
    "tags": [],
}

# Empty tags -> targets the default profile (the common single-profile config).
CONFIG = [
    {
        "preferred_protocol": "torrent",
        "usenet_delay": 0,
        "torrent_delay": 30,
        "bypass_if_highest_quality": True,
    }
]


def _radarr(config):
    return DelayProfileProvider(
        base_url=RADARR, api_key="k", config=config, kind="radarr.delay_profile"
    )


def _sonarr(config):
    return DelayProfileProvider(
        base_url=SONARR, api_key="k", config=config, kind="sonarr.delay_profile"
    )


@responses.activate
def test_empty_tags_updates_the_default_profile_instead_of_creating(plan_provider):
    # The core fix: identity is the tag-set, not the value tuple, so a changed
    # delay re-targets the existing default profile rather than duplicating it.
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    plan = plan_provider(_radarr(CONFIG))
    assert [r.key for r in plan.resources] == [()]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_desired_merges_overrides_over_current():
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    [desired] = _radarr(CONFIG).build_desired()
    # Config overrides applied.
    assert desired["preferredProtocol"] == "torrent"
    assert desired["torrentDelay"] == 30
    assert desired["bypassIfHighestQuality"] is True
    # Server-managed / unspecified keys carried over from current for the full PUT.
    assert desired["id"] == 1
    assert desired["enableUsenet"] is True
    assert desired["order"] == 2147483647


@responses.activate
def test_bypass_score_int_encodes_the_bool_flag():
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    cfg = [{"bypass_if_above_custom_format_score": 5, "minimum_custom_format_score": 5}]
    [desired] = _radarr(cfg).build_desired()
    assert desired["bypassIfAboveCustomFormatScore"] is True
    assert desired["minimumCustomFormatScore"] == 5


@responses.activate
def test_new_tag_set_is_created(plan_provider):
    # A profile for a tag-set absent from current is a CREATE, not an UPDATE.
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    cfg = [{"preferred_protocol": "torrent", "torrent_delay": 30, "tags": [5]}]
    plan = plan_provider(_radarr(cfg))
    assert [r.key for r in plan.resources] == [(5,)]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    plan = plan_provider(_radarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    matched = {
        **RADARR_DEFAULT,
        "preferredProtocol": "torrent",
        "torrentDelay": 30,
        "bypassIfHighestQuality": True,
    }
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[matched])
    plan = plan_provider(_radarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_sonarr_shares_the_endpoint(plan_provider):
    responses.get(f"{SONARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    plan = plan_provider(_sonarr(CONFIG))
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    updated = {
        **RADARR_DEFAULT,
        "preferredProtocol": "torrent",
        "torrentDelay": 30,
        "bypassIfHighestQuality": True,
    }
    responses.put(f"{RADARR}/api/v3/delayprofile/1", json=updated)
    p = _radarr(CONFIG)
    apply_changes(p, plan_provider(p))

    responses.reset()
    responses.get(f"{RADARR}/api/v3/delayprofile", json=[updated])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{RADARR}/api/v3/delayprofile", json=[RADARR_DEFAULT])
    plan_provider(_radarr(CONFIG))
    assert current.call_count == 1
