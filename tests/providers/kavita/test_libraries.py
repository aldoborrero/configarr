import copy
import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.kavita.libraries import KavitaLibraryProvider

KV = "http://kavita.test"

# A LibraryDto as GET /api/library/libraries returns it.
MANGA = {
    "id": 3,
    "name": "Manga",
    "type": 0,
    "lastScanned": "2026-10-01T00:00:00",
    "folderWatching": True,
    "includeInDashboard": True,
    "includeInRecommended": True,
    "manageCollections": False,
    "manageReadingLists": False,
    "includeInSearch": True,
    "allowScrobbling": True,
    "folders": ["/data/manga"],
    "collapseSeriesRelationships": False,
    "libraryFileTypes": [4, 1],
    "excludePatterns": [],
    "allowMetadataMatching": True,
    "enableMetadata": True,
    "removePrefixForSortName": False,
    "inheritWebLinksFromFirstChapter": False,
    "defaultLanguage": None,
    "metadataProvider": 3,
}


@pytest.fixture
def libraries(kavita_auth):
    responses.get(f"{KV}/api/library/libraries", json=[copy.deepcopy(MANGA)])


def _provider(config):
    return KavitaLibraryProvider(KV, "key", config, "kavita.library")


@responses.activate
def test_new_library_is_created_with_type_defaults(
    libraries, plan_provider, apply_changes
):
    responses.post(f"{KV}/api/library/create", json={**MANGA, "id": 9})
    responses.post(f"{KV}/api/library/update", json={})
    provider = _provider(
        [{"name": "Libros", "type": "book", "folders": ["/data/books"]}]
    )
    plan = plan_provider(provider)
    ops = {r.key: r.op for r in plan.resources}
    assert ops == {"Libros": Op.CREATE}

    apply_changes(provider, plan)
    create, update = (json.loads(c.request.body) for c in responses.calls[-2:])
    assert create["name"] == "Libros"
    assert create["type"] == 2
    assert create["folders"] == ["/data/books"]
    assert sorted(create["fileGroupTypes"]) == [2, 3]  # epub + pdf
    assert create["metadataProvider"] == 2  # hardcover
    assert create["includeInSearch"] is True
    # Create ignores some fields, so the same body follows as an update.
    assert update == {**create, "id": 9}


@responses.activate
def test_matching_library_is_unchanged(libraries, plan_provider):
    plan = plan_provider(
        _provider(
            [
                {
                    "name": "Manga",
                    "type": "manga",
                    "folders": ["/data/manga"],
                    "file_group_types": ["archive", "images"],
                }
            ]
        )
    )
    assert not plan.has_changes


@responses.activate
def test_update_keeps_unset_fields_and_posts_whole_dto(
    libraries, plan_provider, apply_changes
):
    responses.post(f"{KV}/api/library/update", json={})
    provider = _provider([{"name": "Manga", "folder_watching": False}])
    plan = plan_provider(provider)
    [res] = plan.resources
    assert res.op is Op.UPDATE
    assert [(d.path, d.before, d.after) for d in res.field_diffs] == [
        ("folderWatching", True, False)
    ]
    apply_changes(provider, plan)
    body = json.loads(responses.calls[-1].request.body)
    assert body["id"] == 3
    assert body["folderWatching"] is False
    assert body["folders"] == ["/data/manga"]
    assert body["fileGroupTypes"] == [4, 1]
    assert body["metadataProvider"] == 3


@responses.activate
def test_type_change_resets_an_invalid_metadata_provider(libraries, plan_provider):
    plan = plan_provider(_provider([{"name": "Manga", "type": "comic"}]))
    [res] = plan.resources
    diffs = {d.path: (d.before, d.after) for d in res.field_diffs}
    assert diffs["type"] == ("manga", "comic")
    assert diffs["metadataProvider"] == ("mangabaka", "comic_book_roundup")


@responses.activate
def test_invalid_metadata_provider_is_rejected(libraries, plan_provider):
    with pytest.raises(ValueError, match="not valid for a manga library"):
        plan_provider(_provider([{"name": "Manga", "metadata_provider": "hardcover"}]))


@responses.activate
def test_new_library_needs_type_and_folders(libraries, plan_provider):
    with pytest.raises(ValueError, match="missing required 'type'"):
        plan_provider(_provider([{"name": "New", "folders": ["/x"]}]))


@responses.activate
def test_prune_deletes_unmanaged_library(libraries, plan_provider, apply_changes):
    responses.post(f"{KV}/api/library/create", json={"id": 9})
    responses.post(f"{KV}/api/library/update", json={})
    responses.delete(f"{KV}/api/library/delete", json=True)
    provider = _provider([{"name": "Comics", "type": "comic", "folders": ["/c"]}])
    plan = plan_provider(provider, prune=True)
    ops = {r.key: r.op for r in plan.resources}
    assert ops == {"Comics": Op.CREATE, "Manga": Op.DELETE}
    apply_changes(provider, plan)
    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].request.url.endswith("libraryId=3")
    create = next(
        json.loads(c.request.body)
        for c in responses.calls
        if c.request.url.endswith("/create")
    )
    assert create["allowScrobbling"] is False  # Kavita forces it off for comics


@responses.activate
def test_without_config_does_nothing(plan_provider):
    plan = plan_provider(_provider([]))
    assert plan.resources == []
    assert len(responses.calls) == 0
