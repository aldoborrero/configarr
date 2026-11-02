from urllib.parse import parse_qs

import responses

from configarr.plan import Op
from configarr.providers.bazarr.default_profiles import BazarrDefaultProfileProvider

BAZARR = "http://bazarr.test"

PROFILES = [
    {"profileId": 1, "name": "Spanish + English", "items": []},
    {"profileId": 2, "name": "English", "items": []},
]
SERIES = [
    {"sonarrSeriesId": 10, "title": "Friends", "profileId": None},
    {"sonarrSeriesId": 11, "title": "Bluey", "profileId": 2},  # chosen by hand
    {"sonarrSeriesId": 12, "title": "Man vs. Wild", "profileId": None},
]
MOVIES = [
    {"radarrId": 20, "title": "Akira", "profileId": None},
    {"radarrId": 21, "title": "Pluto", "profileId": 1},
]


def _provider(config):
    return BazarrDefaultProfileProvider(BAZARR, "k", config, "bazarr.default_profile")


def _mock_get(series=SERIES, movies=MOVIES, profiles=PROFILES):
    responses.add(
        responses.GET, f"{BAZARR}/api/system/languages/profiles", json=profiles
    )
    responses.add(
        responses.GET,
        f"{BAZARR}/api/series",
        json={"data": series, "total": len(series)},
    )
    responses.add(
        responses.GET,
        f"{BAZARR}/api/movies",
        json={"data": movies, "total": len(movies)},
    )


def _posts():
    return [c for c in responses.calls if c.request.method == "POST"]


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get()
    plan = plan_provider(_provider({}))
    assert not plan.resources
    assert not responses.calls  # nothing configured, nothing fetched


@responses.activate
def test_only_unset_items_get_the_profile(plan_provider):
    _mock_get()
    plan = plan_provider(
        _provider({"series": "Spanish + English", "movies": "Spanish + English"})
    )
    changed = sorted(r.key for r in plan.resources if r.changed)
    assert changed == [("movies", 20), ("series", 10), ("series", 12)]
    assert all(r.op is Op.UPDATE for r in plan.resources if r.changed)


@responses.activate
def test_hand_chosen_profile_is_never_overridden(plan_provider):
    _mock_get()
    plan = plan_provider(_provider({"series": "Spanish + English"}))
    assert ("series", 11) not in {r.key for r in plan.resources if r.changed}


@responses.activate
def test_series_only_config_leaves_movies_alone(plan_provider):
    _mock_get()
    plan = plan_provider(_provider({"series": "Spanish + English"}))
    assert {r.key[0] for r in plan.resources if r.changed} == {"series"}
    assert not any("/api/movies" in c.request.url for c in responses.calls)


@responses.activate
def test_unknown_profile_name_plans_nothing(plan_provider):
    _mock_get()
    plan = plan_provider(_provider({"series": "Klingon"}))
    assert not plan.has_changes


@responses.activate
def test_apply_posts_one_form_per_item(plan_provider, apply_changes):
    _mock_get()
    responses.add(responses.POST, f"{BAZARR}/api/series", status=204)
    responses.add(responses.POST, f"{BAZARR}/api/movies", status=204)
    p = _provider({"series": "Spanish + English", "movies": "Spanish + English"})
    apply_changes(p, plan_provider(p))

    forms = sorted(
        (
            c.request.url.split("?")[0].rsplit("/", 1)[1],
            sorted(parse_qs(c.request.body).items()),
        )
        for c in _posts()
    )
    assert forms == [
        ("movies", [("profileid", ["1"]), ("radarrid", ["20"])]),
        ("series", [("profileid", ["1"]), ("seriesid", ["10"])]),
        ("series", [("profileid", ["1"]), ("seriesid", ["12"])]),
    ]


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get()
    responses.add(responses.POST, f"{BAZARR}/api/series", status=204)
    p = _provider({"series": "Spanish + English"})
    apply_changes(p, plan_provider(p))

    # The server now reports the profile on the two series that had none.
    responses.reset()
    _mock_get(series=[{**s, "profileId": s["profileId"] or 1} for s in SERIES])
    assert not plan_provider(_provider({"series": "Spanish + English"})).has_changes
