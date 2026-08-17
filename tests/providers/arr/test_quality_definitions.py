import responses

from configarr.model import Op
from configarr.providers.arr.quality_definitions import QualityDefinitionProvider

BASE = "http://radarr.test"

# /qualitydefinition returns every built-in quality with its size limits.
CURRENT = [
    {
        "id": 1,
        "quality": {"id": 1, "name": "SDTV", "source": "television", "resolution": 480},
        "title": "SDTV",
        "weight": 1,
        "minSize": 0.0,
        "maxSize": 100.0,
        "preferredSize": 95.0,
    },
    {
        "id": 2,
        "quality": {
            "id": 2,
            "name": "WEBDL-1080p",
            "source": "web",
            "resolution": 1080,
        },
        "title": "WEBDL-1080p",
        "weight": 2,
        "minSize": 0.0,
        "maxSize": 100.0,
        "preferredSize": 95.0,
    },
]

CONFIG = {"WEBDL-1080p": {"min": 5, "max": 200, "preferred": 95}}


def _provider(config):
    return QualityDefinitionProvider(
        base_url=BASE, api_key="k", config=config, kind="radarr.quality_definition"
    )


@responses.activate
def test_only_listed_quality_is_planned(plan_provider):
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=CURRENT)
    plan = plan_provider(_provider(CONFIG))
    # SDTV is untouched (not listed); only WEBDL-1080p is diffed.
    assert [r.key for r in plan.resources] == ["WEBDL-1080p"]
    assert plan.resources[0].op is Op.UPDATE


@responses.activate
def test_desired_merges_sizes_over_current():
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=CURRENT)
    [desired] = _provider(CONFIG).build_desired()
    assert desired["minSize"] == 5
    assert desired["maxSize"] == 200
    assert desired["preferredSize"] == 95
    # Server-managed fields carried over from current for the full PUT.
    assert desired["id"] == 2
    assert desired["title"] == "WEBDL-1080p"
    assert desired["weight"] == 2


@responses.activate
def test_idempotent_when_sizes_match(plan_provider):
    matched = [
        CURRENT[0],
        {**CURRENT[1], "minSize": 5.0, "maxSize": 200.0, "preferredSize": 95.0},
    ]
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=matched)
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_unknown_quality_is_skipped(plan_provider):
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=CURRENT)
    plan = plan_provider(_provider({"Remux-2160p": {"min": 1}}))
    # No such quality on the instance -> nothing to update (mirror legacy skip).
    assert not plan.resources


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=CURRENT)
    updated = {**CURRENT[1], "minSize": 5.0, "maxSize": 200.0, "preferredSize": 95.0}
    responses.put(f"{BASE}/api/v3/qualitydefinition/2", json=updated)
    p = _provider(CONFIG)
    apply_changes(p, plan_provider(p))

    responses.reset()
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=[CURRENT[0], updated])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources


@responses.activate
def test_plan_fetches_current_once(plan_provider):
    # build_desired() reads current to merge over it, and the runner diffs against
    # current too. Both must share one GET — not re-fetch (TOCTOU + 2x load).
    current = responses.get(f"{BASE}/api/v3/qualitydefinition", json=CURRENT)
    plan_provider(_provider(CONFIG))
    assert current.call_count == 1
