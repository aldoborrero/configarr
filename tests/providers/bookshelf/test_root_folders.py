import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.bookshelf.root_folders import BookshelfRootFolderProvider

BOOKSHELF = "http://bookshelf.test"
API = f"{BOOKSHELF}/api/v1"

QUALITY_PROFILES = [{"id": 1, "name": "eBook"}, {"id": 2, "name": "Spoken"}]
METADATA_PROFILES = [{"id": 1, "name": "Standard"}, {"id": 2, "name": "None"}]

# A root folder as GET /rootfolder returns it (RootFolderResource).
EXISTING = {
    "id": 7,
    "name": "Libros",
    "path": "/hdd/books",
    "defaultMetadataProfileId": 1,
    "defaultQualityProfileId": 1,
    "defaultMonitorOption": "all",
    "defaultNewItemMonitorOption": "all",
    "defaultTags": [],
    "isCalibreLibrary": False,
    "port": 0,
    "outputProfile": "default",
    "useSsl": False,
    "accessible": True,
    "freeSpace": 1234,
    "totalSpace": 5678,
}

ENTRY = {
    "name": "Libros",
    "path": "/hdd/books/",
    "default_quality_profile": "eBook",
    "default_metadata_profile": "Standard",
}


def _provider(config):
    return BookshelfRootFolderProvider(BOOKSHELF, "k", config, "bookshelf.root_folder")


def _profiles():
    responses.get(f"{API}/qualityprofile", json=QUALITY_PROFILES)
    responses.get(f"{API}/metadataprofile", json=METADATA_PROFILES)


@responses.activate
def test_existing_folder_is_unchanged(plan_provider):
    responses.get(f"{API}/rootfolder", json=[EXISTING])
    _profiles()
    plan = plan_provider(_provider([ENTRY]))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_creates_with_profile_names_resolved(plan_provider, apply_changes):
    responses.get(f"{API}/rootfolder", json=[])
    _profiles()
    post = responses.post(f"{API}/rootfolder", json={"id": 8})
    p = _provider(
        [
            {
                "path": "/hdd/audiobooks",
                "default_quality_profile": "Spoken",
                "default_metadata_profile": "Standard",
                "default_new_item_monitor": "New",
            }
        ]
    )
    plan = plan_provider(p)
    assert [(r.key, r.op) for r in plan.resources] == [("/hdd/audiobooks", Op.CREATE)]

    apply_changes(p, plan)
    body = json.loads(post.calls[0].request.body)
    assert body["name"] == "audiobooks"  # defaulted from the path
    assert body["defaultQualityProfileId"] == 2
    assert body["defaultMetadataProfileId"] == 1
    assert body["defaultNewItemMonitorOption"] == "new"
    assert body["defaultMonitorOption"] == "all"
    assert body["isCalibreLibrary"] is False
    assert body["outputProfile"] == "default"


@responses.activate
def test_changed_defaults_update_in_place(plan_provider, apply_changes):
    responses.get(f"{API}/rootfolder", json=[EXISTING])
    _profiles()
    put = responses.put(f"{API}/rootfolder/7", json={"id": 7})
    p = _provider([{**ENTRY, "default_quality_profile": "Spoken"}])

    plan = plan_provider(p)
    [res] = plan.resources
    assert res.op is Op.UPDATE

    apply_changes(p, plan)
    body = json.loads(put.calls[0].request.body)
    assert body["id"] == 7
    assert body["defaultQualityProfileId"] == 2
    assert body["path"] == "/hdd/books"
    assert body["outputProfile"] == "default"  # unmanaged keys ride through


@responses.activate
def test_unknown_profile_is_kept_by_name_on_plan(plan_provider):
    # A profile the same config creates earlier in the run: the plan shows it by
    # name instead of failing.
    responses.get(f"{API}/rootfolder", json=[])
    _profiles()
    plan = plan_provider(_provider([{**ENTRY, "default_quality_profile": "Comics"}]))
    [res] = plan.resources
    assert res.op is Op.CREATE


@responses.activate
def test_unknown_profile_fails_on_apply_path():
    responses.get(f"{API}/rootfolder", json=[])
    _profiles()
    p = _provider([{**ENTRY, "default_quality_profile": "Comics"}])
    p._create_missing_tags = True  # what the runner sets for apply
    with pytest.raises(ValueError, match="'Comics' does not exist"):
        p.build_desired()


@responses.activate
def test_create_requires_both_profiles():
    responses.get(f"{API}/rootfolder", json=[])
    _profiles()
    p = _provider([{"path": "/hdd/books", "default_quality_profile": "eBook"}])
    with pytest.raises(ValueError, match="default_metadata_profile required"):
        p.build_desired()
