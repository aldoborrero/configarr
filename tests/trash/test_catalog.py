import pytest

from configarr.trash.catalog import Catalog
from configarr.trash.errors import TrashError
from configarr.trash.metadata import load_metadata


@pytest.fixture
def radarr_catalog(guide_root):
    paths = load_metadata(guide_root).json_paths.radarr
    return Catalog(guide_root, paths)


def test_custom_format_by_trash_id(radarr_catalog):
    cf = radarr_catalog.custom_format("aaa111")
    assert cf["name"] == "HDR10"
    assert cf["include_when_renaming"] is False
    assert cf["trash_scores"] == {"default": 100}
    spec = cf["specifications"][0]
    assert spec["implementation"] == "ReleaseTitleSpecification"
    assert spec["fields"] == {"value": "\\bHDR10\\b"}


def test_object_fields_multi_key_preserved(radarr_catalog):
    cf = radarr_catalog.custom_format("bbb222")
    assert cf["specifications"][0]["fields"] == {"value": 1, "exceptLanguage": False}
    assert cf["include_when_renaming"] is True


def test_array_form_fields_normalized_to_dict(radarr_catalog):
    # Historical/defensive: array-form fields collapse to the {name: value} dict.
    cf = radarr_catalog.custom_format("ccc333")
    assert cf["specifications"][0]["fields"] == {"value": "(x|h)265"}
    assert cf["specifications"][0]["required"] is True


def test_unknown_trash_id_raises(radarr_catalog):
    with pytest.raises(TrashError, match="trash_id not found"):
        radarr_catalog.custom_format("nope")


def test_service_separation(guide_root):
    sonarr = Catalog(guide_root, load_metadata(guide_root).json_paths.sonarr)
    assert sonarr.custom_format("sonarr999")["name"] == "Sonarr x265"
    # A radarr-only id is absent from the sonarr catalog.
    with pytest.raises(TrashError):
        sonarr.custom_format("aaa111")


def test_quality_definition_mapping(radarr_catalog):
    qd = radarr_catalog.quality_definition("movie")
    assert qd["SDTV"] == {"min": 2, "max": 100, "preferred": 95}
    assert qd["Bluray-1080p"] == {"min": 5, "max": 200, "preferred": 190}


def test_unknown_quality_type_raises(radarr_catalog):
    with pytest.raises(TrashError, match="type not found"):
        radarr_catalog.quality_definition("tv")


def test_malformed_guide_file_raises_clean_error(tmp_path):
    # A non-object JSON file in a resource dir raises TrashError, not AttributeError.
    (tmp_path / "metadata.json").write_text(
        '{"json_paths": {"radarr": {"custom_formats": ["cf"]}}}'
    )
    cf_dir = tmp_path / "cf"
    cf_dir.mkdir()
    (cf_dir / "bad.json").write_text('["not", "an", "object"]')
    catalog = Catalog(tmp_path, load_metadata(tmp_path).json_paths.radarr)
    with pytest.raises(TrashError, match="expected a JSON object"):
        catalog.custom_formats()


def test_non_numeric_score_raises_trash_error(tmp_path):
    # A malformed guide value must surface as TrashError (caught by the CLI), not a
    # bare ValueError that escapes as a traceback.
    (tmp_path / "metadata.json").write_text(
        '{"json_paths": {"radarr": {"custom_formats": ["cf"]}}}'
    )
    cf_dir = tmp_path / "cf"
    cf_dir.mkdir()
    (cf_dir / "bad.json").write_text(
        '{"trash_id": "x", "name": "Bad", "trash_scores": {"default": "high"}}'
    )
    catalog = Catalog(tmp_path, load_metadata(tmp_path).json_paths.radarr)
    with pytest.raises(TrashError, match="non-numeric"):
        catalog.custom_formats()
