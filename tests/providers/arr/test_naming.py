import responses

from configarr.plan import Op
from configarr.providers.arr.naming import NamingProvider

RADARR = "http://radarr.test"
SONARR = "http://sonarr.test"

# /config/naming is a fixed-id singleton (GET returns one object, not a list).
RADARR_CURRENT = {
    "id": 1,
    "renameMovies": False,
    "replaceIllegalCharacters": True,
    "colonReplacementFormat": "delete",
    "standardMovieFormat": "{Movie Title}",
    "movieFolderFormat": "{Movie Title}",
}

RADARR_CONFIG = {
    "rename_movies": True,
    "colon_replacement": "smart",
    "standard_movie_format": "{Movie Title} ({Release Year})",
}

SONARR_CURRENT = {
    "id": 1,
    "renameEpisodes": True,
    "replaceIllegalCharacters": True,
    "colonReplacementFormat": 0,
    "multiEpisodeStyle": 0,
    "standardEpisodeFormat": "{Series Title}",
    "dailyEpisodeFormat": "{Series Title}",
    "animeEpisodeFormat": "{Series Title}",
    "seriesFolderFormat": "{Series Title}",
    "seasonFolderFormat": "Season {season}",
    "specialsFolderFormat": "Specials",
}

SONARR_CONFIG = {
    "colon_replacement": "smart",
    "multi_episode_style": "range",
}


def _radarr(config):
    return NamingProvider(
        base_url=RADARR, api_key="k", config=config, kind="radarr.naming"
    )


def _sonarr(config):
    return NamingProvider(
        base_url=SONARR, api_key="k", config=config, kind="sonarr.naming"
    )


@responses.activate
def test_singleton_is_planned_as_update(plan_provider):
    responses.get(f"{RADARR}/api/v3/config/naming", json=RADARR_CURRENT)
    plan = plan_provider(_radarr(RADARR_CONFIG))
    assert [r.key for r in plan.resources] == [1]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_desired_merges_overrides_over_current():
    responses.get(f"{RADARR}/api/v3/config/naming", json=RADARR_CURRENT)
    [desired] = _radarr(RADARR_CONFIG).build_desired()
    # Config overrides applied (with colon mapped to the Radarr string form).
    assert desired["renameMovies"] is True
    assert desired["colonReplacementFormat"] == "smart"
    assert desired["standardMovieFormat"] == "{Movie Title} ({Release Year})"
    # Server-managed / unspecified keys carried over from current for the full PUT.
    assert desired["id"] == 1
    assert desired["replaceIllegalCharacters"] is True
    assert desired["movieFolderFormat"] == "{Movie Title}"


@responses.activate
def test_sonarr_maps_colon_and_multi_episode_to_ints():
    responses.get(f"{SONARR}/api/v3/config/naming", json=SONARR_CURRENT)
    [desired] = _sonarr(SONARR_CONFIG).build_desired()
    assert desired["colonReplacementFormat"] == 4
    assert desired["multiEpisodeStyle"] == 5


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{RADARR}/api/v3/config/naming", json=RADARR_CURRENT)
    plan = plan_provider(_radarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    matched = {
        **RADARR_CURRENT,
        "renameMovies": True,
        "colonReplacementFormat": "smart",
        "standardMovieFormat": "{Movie Title} ({Release Year})",
    }
    responses.get(f"{RADARR}/api/v3/config/naming", json=matched)
    plan = plan_provider(_radarr(RADARR_CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{RADARR}/api/v3/config/naming", json=RADARR_CURRENT)
    updated = {
        **RADARR_CURRENT,
        "renameMovies": True,
        "colonReplacementFormat": "smart",
        "standardMovieFormat": "{Movie Title} ({Release Year})",
    }
    responses.put(f"{RADARR}/api/v3/config/naming/1", json=updated)
    p = _radarr(RADARR_CONFIG)
    apply_changes(p, plan_provider(p))

    responses.reset()
    responses.get(f"{RADARR}/api/v3/config/naming", json=updated)
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{RADARR}/api/v3/config/naming", json=RADARR_CURRENT)
    plan_provider(_radarr(RADARR_CONFIG))
    assert current.call_count == 1
