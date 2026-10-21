import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.bookshelf.metadata_profiles import MetadataProfileProvider

BOOKSHELF = "http://bookshelf.test"
API = f"{BOOKSHELF}/api/v1/metadataprofile"

# GET /metadataprofile/schema (MetadataProfileSchemaController: a default profile
# with allowedLanguages "eng").
SCHEMA = {
    "id": 0,
    "name": None,
    "minPopularity": 0.0,
    "skipMissingDate": False,
    "skipMissingIsbn": False,
    "skipPartsAndSets": False,
    "skipSeriesSecondary": False,
    "allowedLanguages": "eng",
    "minPages": 0,
    "ignored": [],
}

NONE_PROFILE = {
    **SCHEMA,
    "id": 2,
    "name": "None",
    "minPopularity": 1e10,
}

STANDARD = {
    **SCHEMA,
    "id": 1,
    "name": "Standard",
    "minPopularity": 350.0,
    "skipMissingDate": True,
    "skipPartsAndSets": True,
    "skipSeriesSecondary": True,
    "allowedLanguages": "eng,en-US,en-GB",
}

CONFIG = {
    "Standard": {
        "min_popularity": 0,
        "allowed_languages": ["spa", "eng"],
        "skip_missing_isbn": False,
    }
}


def _provider(config):
    return MetadataProfileProvider(BOOKSHELF, "k", config, "bookshelf.metadata_profile")


@responses.activate
def test_creates_from_schema_with_comma_joined_languages(plan_provider, apply_changes):
    responses.get(API, json=[NONE_PROFILE])
    responses.get(f"{API}/schema", json=SCHEMA)
    post = responses.post(API, json={"id": 3})
    p = _provider({"Libros": {"allowed_languages": ["spa", "eng"], "min_pages": 50}})

    plan = plan_provider(p)
    assert [(r.key, r.op) for r in plan.resources] == [("Libros", Op.CREATE)]

    apply_changes(p, plan)
    body = json.loads(post.calls[0].request.body)
    assert body["name"] == "Libros"
    assert body["allowedLanguages"] == "spa,eng"
    assert body["minPages"] == 50
    assert body["skipMissingIsbn"] is False  # schema default carried
    assert "id" not in body


@responses.activate
def test_updates_matched_profile_over_current(plan_provider, apply_changes):
    responses.get(API, json=[STANDARD, NONE_PROFILE])
    put = responses.put(f"{API}/1", json={"id": 1})
    p = _provider(CONFIG)

    plan = plan_provider(p)
    [res] = plan.resources
    assert (res.key, res.op) == ("Standard", Op.UPDATE)

    apply_changes(p, plan)
    body = json.loads(put.calls[0].request.body)
    assert body["id"] == 1
    assert body["minPopularity"] == 0
    assert body["allowedLanguages"] == "spa,eng"
    # Unset keys keep their server value.
    assert body["skipPartsAndSets"] is True


@responses.activate
def test_languages_compare_as_a_set(plan_provider):
    responses.get(
        API,
        json=[{**STANDARD, "minPopularity": 0.0, "allowedLanguages": "eng, spa"}],
    )
    plan = plan_provider(_provider(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_none_profile_is_never_pruned(plan_provider):
    responses.get(API, json=[STANDARD, NONE_PROFILE])
    plan = plan_provider(_provider({}), prune=True)
    assert [(r.key, r.op) for r in plan.resources] == [("Standard", Op.DELETE)]


@responses.activate
def test_none_profile_cannot_be_managed():
    responses.get(API, json=[])
    with pytest.raises(ValueError, match="reserved"):
        _provider({"None": {}}).build_desired()


@responses.activate
def test_in_use_delete_surfaces_a_clear_error(plan_provider, apply_changes):
    responses.get(API, json=[STANDARD])
    responses.delete(
        f"{API}/1",
        status=400,
        json={"message": "Metadata profile [Standard] is in use."},
    )
    p = _provider({})
    plan = plan_provider(p, prune=True)
    with pytest.raises(RuntimeError, match=r"Standard.*is in use.*reassign"):
        apply_changes(p, plan)
