import responses

from configarr.plan import Op
from configarr.providers.bazarr.settings import BazarrSettingsProvider

BAZARR = "http://bazarr.test"

# The settings document Bazarr returns from GET /api/system/settings: a nested dict
# keyed by section. Each managed provider here owns one section (general/sonarr/
# radarr). Bools are echoed as real JSON booleans; the form-POST encodes them as
# lower-cased strings. Sections carry far more keys than configarr manages, so the
# diff is over the config keys only.
CURRENT_SETTINGS = {
    "general": {
        "use_sonarr": True,
        "use_radarr": True,
        "page_size": 25,
        "theme": "auto",
        "branch": "master",
    },
    "sonarr": {
        "ip": "sonarr.local",
        "port": 8989,
        "base_url": "/",
        "ssl": False,
        "apikey": "sonarr-key",
    },
    "radarr": {
        "ip": "radarr.local",
        "port": 7878,
        "ssl": False,
    },
    "subsync": {
        "use_subsync": False,
        "subsync_threshold": 90,
        "gss": True,
    },
}


def _provider(section, config):
    return BazarrSettingsProvider(
        base_url=BAZARR,
        api_key="k",
        config=config,
        kind=f"bazarr.{section}",
    )


def _mock_get_settings(settings=CURRENT_SETTINGS):
    responses.get(
        f"{BAZARR}/api/system/settings",
        json=settings,
    )


def _mock_post_settings():
    responses.post(f"{BAZARR}/api/system/settings", json={})


@responses.activate
def test_section_plans_as_update(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("general", {"page_size": 50}))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_section_is_singleton():
    p = _provider("general", {"page_size": 50})
    [desired] = p.build_desired()
    # Both sides map to the same fixed section key, so the engine emits UPDATE.
    assert p.match_key(desired) == p.match_key({"anything": 1})


@responses.activate
def test_update_changes_only_set_field(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("general", {"page_size": 50}))
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "page_size" in paths
    assert "theme" not in paths


@responses.activate
def test_unmanaged_server_keys_stay_out_of_diff(plan_provider):
    _mock_get_settings()
    # Config sets only keys already at their server value, so a re-plan is a no-op
    # even though the server returns many unmanaged keys (theme, branch).
    plan = plan_provider(_provider("general", {"use_sonarr": True, "page_size": 25}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("sonarr", {"ip": "sonarr.local", "port": 8989}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_bool_diff_is_canonical(plan_provider):
    _mock_get_settings()
    # Server echoes a real bool; config sets the same value — no spurious diff.
    plan = plan_provider(_provider("sonarr", {"ssl": False}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("general", {}))
    assert not plan.resources


@responses.activate
def test_radarr_section_is_independent(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("radarr", {"port": 7000}))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert paths == {"port"}


@responses.activate
def test_matching_apikey_is_noop(plan_provider):
    # The sonarr/radarr sections carry an apikey (cleartext); an equal value is
    # idempotent because both sides fingerprint identically.
    _mock_get_settings()
    plan = plan_provider(_provider("sonarr", {"apikey": "sonarr-key"}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_changed_apikey_diff_is_fingerprint_not_cleartext(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("sonarr", {"apikey": "rotated"}))
    d = next(d for d in plan.resources[0].field_diffs if d.path == "apikey")
    assert d.before != "sonarr-key" and d.after != "rotated"
    assert str(d.after).startswith("secret:")
    assert "sonarr-key" not in str(d.before) and "rotated" not in str(d.after)


@responses.activate
def test_apply_writes_real_apikey_not_fingerprint(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider("sonarr", {"apikey": "rotated"})
    apply_changes(p, plan_provider(p))
    body = [c for c in responses.calls if c.request.method == "POST"][-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    assert "settings-sonarr-apikey" in rendered
    assert "rotated" in rendered
    assert "secret:" not in rendered


@responses.activate
def test_apply_posts_section_form_fields(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider("general", {"page_size": 50, "use_sonarr": False})
    apply_changes(p, plan_provider(p))
    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert post_calls
    body = post_calls[-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    # Form fields are settings-<section>-<field>; bools are lower-cased strings.
    assert "settings-general-page_size" in rendered
    assert "50" in rendered
    assert "settings-general-use_sonarr" in rendered
    assert "false" in rendered


@responses.activate
def test_subsync_apply_posts_use_subsync(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider("subsync", {"use_subsync": True})
    apply_changes(p, plan_provider(p))
    body = [c for c in responses.calls if c.request.method == "POST"][-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    assert "settings-subsync-use_subsync" in rendered
    assert "true" in rendered


@responses.activate
def test_subsync_idempotent_when_current_matches(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider("subsync", {"use_subsync": False, "gss": True}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider("general", {"page_size": 50})
    apply_changes(p, plan_provider(p))

    responses.reset()
    applied = {s: dict(v) for s, v in CURRENT_SETTINGS.items()}
    applied["general"]["page_size"] = 50
    _mock_get_settings(applied)
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
