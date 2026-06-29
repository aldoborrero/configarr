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
    assert plan.resources[0].op is Op.CREATE


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
