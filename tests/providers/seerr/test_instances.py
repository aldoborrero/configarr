import pytest
import responses
from responses import matchers

from configarr.plan import Op
from configarr.providers.seerr.instances import (
    SeerrRadarrProvider,
    SeerrSonarrProvider,
)

SEERR = "http://seerr.test"

# What Seerr's connection probe reports about the target *arr.
PROFILES = [{"id": 7, "name": "WEB-1080p"}, {"id": 9, "name": "Anime-1080p"}]
FOLDERS = [{"path": "/media/movies"}, {"path": "/media/anime/movies"}]
SON_FOLDERS = [{"path": "/media/tv"}, {"path": "/media/anime/shows"}]
TAGS = [{"id": 3, "label": "4k"}, {"id": 5, "label": "kids"}]

RADARR_CONFIG = {
    "radarr": {
        "hostname": "radarr.test",
        "api_key": "arrkey",
        "quality_profile": "WEB-1080p",
        "root_folder": "/media/movies",
        "is_default": True,
    }
}


def _radarr(config=None):
    return SeerrRadarrProvider(
        base_url=SEERR, api_key="k", config=config or RADARR_CONFIG, kind="seerr.radarr"
    )


def _mock_probe(kind="radarr", folders=None):
    """Seerr's own connection test, which is where the ids come from."""
    responses.add(
        responses.POST,
        f"{SEERR}/api/v1/settings/{kind}/test",
        json={
            "profiles": PROFILES,
            "rootFolders": folders or FOLDERS,
            "tags": TAGS,
            "urlBase": "",
        },
    )


@responses.activate
def test_creates_instance_resolving_profile_and_folder():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    desired = _radarr().build_desired()
    assert len(desired) == 1
    payload = desired[0]
    # Seerr needs the profile by id AND by name; the config only named it.
    assert payload["activeProfileId"] == 7
    assert payload["activeProfileName"] == "WEB-1080p"
    assert payload["activeDirectory"] == "/media/movies"
    assert payload["name"] == "radarr"
    assert payload["port"] == 7878  # default filled in
    assert payload["isDefault"] is True
    assert payload["minimumAvailability"] == "released"  # kind default
    assert payload["apiKey"] == "arrkey"


@responses.activate
def test_unchanged_when_seerr_already_matches():
    current = {
        "id": 1,
        "name": "radarr",
        "hostname": "radarr.test",
        "port": 7878,
        "apiKey": "arrkey",
        "useSsl": False,
        "baseUrl": "",
        "activeProfileId": 7,
        "activeProfileName": "WEB-1080p",
        "activeDirectory": "/media/movies",
        "is4k": False,
        "minimumAvailability": "released",
        "isDefault": True,
        "externalUrl": "",
        "syncEnabled": False,
        "preventSearch": False,
        "tags": [],
        "tagRequests": False,
        # Seerr echoes this back; it belongs to the override-rule resource.
        "overrideRule": [],
    }
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[current])
    _mock_probe()
    p = _radarr()
    desired = p.build_desired()[0]
    # id is server-assigned and must not read as drift.
    assert p.normalize(current) == p.normalize(desired)


@responses.activate
def test_update_puts_to_the_server_assigned_id():
    current = {"id": 42, "name": "radarr"}
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[current])
    _mock_probe()
    p = _radarr()
    from configarr.plan import ResourcePlan

    action = p.to_action(
        ResourcePlan(kind="seerr.radarr", key="radarr", op=Op.UPDATE),
        current,
        p.build_desired()[0],
    )
    responses.add(
        responses.PUT,
        f"{SEERR}/api/v1/settings/radarr/42",
        json={"id": 42},
        match=[matchers.json_params_matcher({}, strict_match=False)],
    )
    p.apply(action)
    put = [c.request for c in responses.calls if c.request.method == "PUT"]
    assert len(put) == 1
    # The id addresses the route; it must not be echoed inside the body.
    assert '"id"' not in put[0].body.decode()


@responses.activate
def test_unknown_profile_is_a_hard_error_naming_the_alternatives():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    config = {"radarr": {**RADARR_CONFIG["radarr"], "quality_profile": "Nope"}}
    with pytest.raises(ValueError, match=r"Nope.*does not exist.*WEB-1080p"):
        _radarr(config).build_desired()


@responses.activate
def test_unknown_root_folder_is_a_hard_error():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    config = {"radarr": {**RADARR_CONFIG["radarr"], "root_folder": "/nope"}}
    with pytest.raises(ValueError, match=r"/nope.*not configured"):
        _radarr(config).build_desired()


@responses.activate
def test_unknown_setting_is_rejected_because_seerr_would_ignore_it():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    config = {"radarr": {**RADARR_CONFIG["radarr"], "qualityProfile": "WEB-1080p"}}
    with pytest.raises(ValueError, match="unknown setting"):
        _radarr(config).build_desired()


@responses.activate
def test_403_explains_the_owner_account():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", status=403, json={})
    with pytest.raises(RuntimeError, match=r"owner account.*setup wizard"):
        _radarr().fetch_current()


@responses.activate
def test_sonarr_resolves_the_anime_pair_too():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/sonarr", json=[])
    _mock_probe("sonarr", SON_FOLDERS)
    config = {
        "sonarr": {
            "hostname": "sonarr.test",
            "api_key": "arrkey",
            "quality_profile": "WEB-1080p",
            "root_folder": "/media/tv",
            "anime_quality_profile": "Anime-1080p",
            "anime_root_folder": "/media/anime/shows",
        }
    }
    payload = SeerrSonarrProvider(
        base_url=SEERR, api_key="k", config=config, kind="seerr.sonarr"
    ).build_desired()[0]
    assert payload["activeProfileId"] == 7
    assert payload["activeAnimeProfileId"] == 9
    assert payload["activeAnimeProfileName"] == "Anime-1080p"
    assert payload["activeAnimeDirectory"] == "/media/anime/shows"
    assert payload["port"] == 8989
    assert payload["enableSeasonFolders"] is False  # Seerr's own default


@responses.activate
def test_sonarr_without_anime_keys_omits_the_anime_pair():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/sonarr", json=[])
    _mock_probe("sonarr", SON_FOLDERS)
    config = {
        "sonarr": {
            "hostname": "sonarr.test",
            "api_key": "arrkey",
            "quality_profile": "WEB-1080p",
            "root_folder": "/media/tv",
        }
    }
    payload = SeerrSonarrProvider(
        base_url=SEERR, api_key="k", config=config, kind="seerr.sonarr"
    ).build_desired()[0]
    assert "activeAnimeProfileId" not in payload


@responses.activate
def test_missing_required_key_names_it():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    config = {"radarr": {"hostname": "radarr.test", "api_key": "k"}}
    with pytest.raises(ValueError, match="missing required 'quality_profile'"):
        _radarr(config).build_desired()


@responses.activate
def test_tags_accept_labels_and_ids():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    config = {"radarr": {**RADARR_CONFIG["radarr"], "tags": ["kids", 3]}}
    payload = _radarr(config).build_desired()[0]
    assert payload["tags"] == [5, 3]


@responses.activate
def test_unknown_tag_label_is_a_hard_error():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    _mock_probe()
    config = {"radarr": {**RADARR_CONFIG["radarr"], "tags": ["nope"]}}
    with pytest.raises(ValueError, match=r"tag 'nope' does not exist.*4k"):
        _radarr(config).build_desired()


@responses.activate
def test_invalid_enum_value_is_rejected_before_it_is_stored():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    config = {"radarr": {**RADARR_CONFIG["radarr"], "minimum_availability": "Released"}}
    with pytest.raises(ValueError, match="minimum_availability must be one of"):
        _radarr(config).build_desired()


@responses.activate
def test_sonarr_defaults_match_seerrs_own_form():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/sonarr", json=[])
    _mock_probe("sonarr", SON_FOLDERS)
    config = {
        "sonarr": {
            "hostname": "sonarr.test",
            "api_key": "arrkey",
            "quality_profile": "WEB-1080p",
            "root_folder": "/media/tv",
        }
    }
    payload = SeerrSonarrProvider(
        base_url=SEERR, api_key="k", config=config, kind="seerr.sonarr"
    ).build_desired()[0]
    assert payload["seriesType"] == "standard"
    assert payload["animeSeriesType"] == "anime"
    assert payload["monitorNewItems"] == "all"
    assert payload["tagRequests"] is False


@responses.activate
def test_unreachable_arr_names_the_instance_and_the_host():
    responses.add(responses.GET, f"{SEERR}/api/v1/settings/radarr", json=[])
    responses.add(
        responses.POST,
        f"{SEERR}/api/v1/settings/radarr/test",
        status=500,
        json={"message": "Failed to connect to Radarr"},
    )
    match = r"cannot reach its \*arr at radarr.test:7878"
    with pytest.raises(RuntimeError, match=match):
        _radarr().build_desired()
