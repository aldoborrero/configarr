import responses

from configarr.plan import Op
from configarr.providers.arr.release_profiles import ReleaseProfileProvider

SONARR = "http://sonarr.test"

# A release profile already on the instance, matched by name.
EXISTING = {
    "id": 1,
    "name": "Optionals",
    "enabled": True,
    "required": ["amzn"],
    "ignored": [],
    "indexerId": 0,
    "tags": [],
}

CONFIG = [
    {
        "name": "Optionals",
        "required": ["amzn"],
    }
]


def _sonarr(config):
    return ReleaseProfileProvider(
        base_url=SONARR, api_key="k", config=config, kind="sonarr.release_profile"
    )


@responses.activate
def test_creates_when_absent(plan_provider):
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[])
    plan = plan_provider(_sonarr(CONFIG))
    assert [r.key for r in plan.resources] == ["Optionals"]
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_updates_existing_by_name(plan_provider):
    # The real-update path the legacy write-once sync lacked: a changed term
    # re-targets the existing profile (id carried through) instead of skipping.
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[EXISTING])
    cfg = [{"name": "Optionals", "required": ["amzn", "web"]}]
    plan = plan_provider(_sonarr(cfg))
    assert [r.key for r in plan.resources] == ["Optionals"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_desired_merges_over_current():
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[EXISTING])
    cfg = [{"name": "Optionals", "ignored": ["x265"]}]
    [desired] = _sonarr(cfg).build_desired()
    # Config override applied.
    assert desired["ignored"] == ["x265"]
    # Server-managed / unspecified keys carried over from current for the PUT.
    assert desired["id"] == 1
    assert desired["required"] == ["amzn"]
    assert desired["enabled"] is True


@responses.activate
def test_create_uses_defaults():
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[])
    cfg = [{"name": "New", "required": ["web"]}]
    [desired] = _sonarr(cfg).build_desired()
    assert desired["name"] == "New"
    assert desired["required"] == ["web"]
    assert desired["enabled"] is True
    assert desired["ignored"] == []
    assert desired["indexerId"] == 0
    assert desired["tags"] == []
    assert "id" not in desired


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[EXISTING])
    plan = plan_provider(_sonarr(None))
    assert not plan.resources


@responses.activate
def test_idempotent_when_current_matches(plan_provider):
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[EXISTING])
    plan = plan_provider(_sonarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[])
    created = {**EXISTING, "name": "New", "required": ["web"]}
    responses.post(f"{SONARR}/api/v3/releaseprofile", json=created)
    cfg = [{"name": "New", "required": ["web"]}]
    p = _sonarr(cfg)
    apply_changes(p, plan_provider(p))

    responses.reset()
    responses.get(f"{SONARR}/api/v3/releaseprofile", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{SONARR}/api/v3/releaseprofile", json=[EXISTING])
    plan_provider(_sonarr(CONFIG))
    assert current.call_count == 1
