import responses

from configarr.diff.engine import diff
from configarr.diff.model import Op
from configarr.diff.providers.radarr_custom_formats import RadarrCustomFormatProvider

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


def _provider(config):
    return RadarrCustomFormatProvider(base_url=BASE, api_key="k", config=config)


def _plan(p):
    return diff(
        p.kind,
        p.fetch_current(),
        p.build_desired(),
        match_key=p.match_key,
        normalize=p.normalize,
    )


@responses.activate
def test_create_when_absent():
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
    plan = _plan(_provider(config))
    assert len(plan.resources) == 1
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
def test_idempotent_when_current_equals_desired():
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
    plan = _plan(_provider(config))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_apply_then_replan_is_noop():
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
    plan = _plan(p)
    desired_by_key = {d["name"]: d for d in p.build_desired()}
    for rp in plan.resources:
        if rp.changed:
            p.apply(p.to_action(rp, None, desired_by_key[rp.key]))

    # Second run: instance now returns the created CF.
    # Do NOT re-register /customformat/schema — _schema() is cached from the first
    # run, so it issues no second GET; re-registering it would leave an unfired mock
    # (responses asserts all registered mocks fire by default).
    responses.reset()
    responses.get(f"{BASE}/api/v3/customformat", json=[created])
    plan2 = _plan(p)
    assert not plan2.has_changes, plan2.resources
