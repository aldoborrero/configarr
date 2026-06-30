import responses

from configarr.diff.model import Op
from configarr.diff.providers.bazarr_providers import BazarrProviderProvider

BAZARR = "http://bazarr.test"

# The settings document Bazarr returns from GET /api/system/settings. Each subtitle
# provider owns one top-level section keyed by its Bazarr name, and the enabled set
# lives in general.enabled_providers. Sections carry more keys than configarr sets,
# so the diff is over the configured keys only.
CURRENT_SETTINGS = {
    "general": {"enabled_providers": ["opensubtitlescom"]},
    "opensubtitlescom": {
        "username": "user",
        "password": "pw",
        "use_hash": True,
    },
    "whisperai": {"endpoint": "http://wai", "timeout": 3600},
}


def _provider(config):
    return BazarrProviderProvider(
        base_url=BAZARR,
        api_key="k",
        config=config,
        kind="bazarr.provider",
    )


def _mock_get_settings(settings=CURRENT_SETTINGS):
    responses.get(f"{BAZARR}/api/system/settings", json=settings)


def _mock_post_settings():
    responses.post(f"{BAZARR}/api/system/settings", json={})


@responses.activate
def test_configured_provider_plans_as_update(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"username": "other"}}))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_submate_is_renamed_to_whisperai(plan_provider):
    # The config name 'submate' addresses Bazarr's 'whisperai' section: with whisperai
    # already enabled and matching, the plan is a no-op (proves the rename mapped).
    settings = {s: dict(v) for s, v in CURRENT_SETTINGS.items()}
    settings["general"]["enabled_providers"] = ["opensubtitlescom", "whisperai"]
    _mock_get_settings(settings)
    plan = plan_provider(
        _provider({"submate": {"endpoint": "http://wai", "timeout": 3600}})
    )
    assert not plan.has_changes, plan.resources


@responses.activate
def test_other_names_pass_through_verbatim(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"username": "other"}}))
    assert plan.resources[0].key == "opensubtitlescom"


@responses.activate
def test_disabled_provider_diffs_on_enabled(plan_provider):
    _mock_get_settings()
    # addic7ed is absent from enabled_providers, so configuring it surfaces an
    # enabled False->True change even with no field overrides.
    plan = plan_provider(_provider({"addic7ed": {}}))
    assert len(plan.resources) == 1
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "enabled" in paths


@responses.activate
def test_enabled_and_matching_is_noop(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"username": "user"}}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_change_only_set_field(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"username": "new"}}))
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "username" in paths
    assert "use_hash" not in paths


@responses.activate
def test_matching_cleartext_secret_is_noop(plan_provider):
    # Bazarr's GET /api/system/settings returns secrets in CLEARTEXT (no "********"
    # mask, unlike *arr — verified against bazarr/app/config.get_settings, which only
    # strips flask_secret_key). So a configured password that equals the stored value
    # is idempotent purely by direct comparison; the provider does not depend on any
    # mask sentinel to avoid a perpetual diff.
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"password": "pw"}}))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_changed_secret_surfaces_update(plan_provider):
    # The flip side of cleartext handling: a real secret change must NOT be hidden.
    # Secrets are never dropped by name here, so a differing password surfaces.
    _mock_get_settings()
    plan = plan_provider(_provider({"opensubtitlescom": {"password": "changed"}}))
    assert plan.resources[0].op is Op.UPDATE
    paths = {d.path for d in plan.resources[0].field_diffs}
    assert "password" in paths


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    _mock_get_settings()
    plan = plan_provider(_provider({}))
    assert not plan.resources


@responses.activate
def test_apply_posts_provider_and_enabled_fields(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider({"opensubtitlescom": {"username": "new"}})
    apply_changes(p, plan_provider(p))
    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    assert post_calls
    body = post_calls[-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    assert "settings-opensubtitlescom-username" in rendered
    assert "settings-general-enabled_providers" in rendered


@responses.activate
def test_apply_adds_to_enabled_providers_additively(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider({"addic7ed": {}})
    apply_changes(p, plan_provider(p))
    post_calls = [c for c in responses.calls if c.request.method == "POST"]
    body = post_calls[-1].request.body
    rendered = body.decode() if isinstance(body, bytes) else str(body)
    # The existing enabled provider is preserved alongside the newly added one.
    assert "opensubtitlescom" in rendered
    assert "addic7ed" in rendered


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    _mock_get_settings()
    _mock_post_settings()
    p = _provider({"opensubtitlescom": {"username": "new"}})
    apply_changes(p, plan_provider(p))

    responses.reset()
    applied = {s: dict(v) for s, v in CURRENT_SETTINGS.items()}
    applied["opensubtitlescom"]["username"] = "new"
    _mock_get_settings(applied)
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
