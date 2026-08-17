import pytest
import responses

from configarr.plan import Op, ResourcePlan
from configarr.providers.arr.custom_formats import CustomFormatProvider

BASE = "http://radarr.test"

SCHEMA = [
    {
        "name": "Release Title",
        "implementation": "ReleaseTitleSpecification",
        "negate": False,
        "required": False,
        "fields": [{"name": "value", "value": ""}],
    }
]


def _provider(config, kind="radarr.custom_format"):
    return CustomFormatProvider(base_url=BASE, api_key="k", config=config, kind=kind)


@responses.activate
def test_create_when_absent(plan_provider):
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    plan = plan_provider(_provider(config))
    assert len(plan.resources) == 1
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_serves_sonarr_via_the_same_v3_api(plan_provider):
    # Sonarr custom formats use the identical /api/v3/customformat endpoints, so
    # the same provider serves them — only the kind differs.
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    provider = _provider(config, kind="sonarr.custom_format")
    assert provider.kind == "sonarr.custom_format"
    plan = plan_provider(provider)
    assert plan.resources[0].op is Op.CREATE


@responses.activate
def test_schema_is_cached():
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    p = _provider(config)
    p.build_desired()
    p.build_desired()
    schema_calls = sum(
        1 for c in responses.calls if "/customformat/schema" in c.request.url
    )
    assert schema_calls == 1


@responses.activate
def test_idempotent_when_current_equals_desired(plan_provider):
    existing = [
        {
            "id": 7,
            "name": "x265",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "negate": False,
                    "required": False,
                    "fields": [{"name": "value", "value": "(x|h)265"}],
                }
            ],
        }
    ]
    responses.get(f"{BASE}/api/v3/customformat", json=existing)
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    plan = plan_provider(_provider(config))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_prune_deletes_unmanaged_and_keeps_managed(plan_provider, apply_changes):
    existing = [
        {
            "id": 7,
            "name": "x265",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "negate": False,
                    "required": False,
                    "fields": [{"name": "value", "value": "(x|h)265"}],
                }
            ],
        },
        {
            "id": 9,
            "name": "stale",
            "includeCustomFormatWhenRenaming": False,
            "specifications": [],
        },
    ]
    responses.get(f"{BASE}/api/v3/customformat", json=existing)
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    responses.delete(f"{BASE}/api/v3/customformat/9", status=200)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    p = _provider(config)
    plan = plan_provider(p, prune=True)
    ops = {r.key: r.op for r in plan.resources}
    assert ops == {"x265": Op.UNCHANGED, "stale": Op.DELETE}

    apply_changes(p, plan)
    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].request.url == f"{BASE}/api/v3/customformat/9"

    # Re-plan with the managed CF still present, stale gone: nothing left to prune.
    responses.reset()
    responses.get(f"{BASE}/api/v3/customformat", json=[existing[0]])
    plan2 = plan_provider(p, prune=True)
    assert not plan2.has_changes, plan2.resources


def test_to_action_delete_without_current_raises_clear_error():
    p = _provider({})
    plan = ResourcePlan(kind=p.kind, key="stale", op=Op.DELETE)
    with pytest.raises(AssertionError, match="requires the current resource"):
        p.to_action(plan, current=None, desired=None)


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    created = {
        "id": 7,
        "name": "x265",
        "includeCustomFormatWhenRenaming": False,
        "specifications": [
            {
                "name": "x265",
                "implementation": "ReleaseTitleSpecification",
                "negate": False,
                "required": False,
                "fields": [{"name": "value", "value": "(x|h)265"}],
            }
        ],
    }
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    responses.post(f"{BASE}/api/v3/customformat", json=created, status=201)
    config = {
        "x265": {
            "specifications": [
                {
                    "name": "x265",
                    "implementation": "ReleaseTitleSpecification",
                    "fields": {"value": "(x|h)265"},
                }
            ]
        }
    }
    p = _provider(config)
    apply_changes(p, plan_provider(p))

    # Second run: instance now returns the created CF.
    # Do NOT re-register /customformat/schema — _schema() is cached from the first
    # run, so it issues no second GET; re-registering it would leave an unfired mock
    # (responses asserts all registered mocks fire by default).
    responses.reset()
    responses.get(f"{BASE}/api/v3/customformat", json=[created])
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
