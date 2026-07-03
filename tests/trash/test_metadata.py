import pytest

from configarr.trash.errors import TrashError
from configarr.trash.metadata import load_metadata


def test_load_metadata_reads_service_paths(guide_root):
    md = load_metadata(guide_root)
    assert md.json_paths.radarr.custom_formats == ["docs/json/radarr/cf"]
    assert md.json_paths.radarr.qualities == ["docs/json/radarr/quality-size"]
    assert md.json_paths.sonarr.custom_formats == ["docs/json/sonarr/cf"]


def test_load_metadata_ignores_unknown_keys(guide_root):
    # Real metadata.json carries $schema, naming, conflicts, ... — must not error.
    md = load_metadata(guide_root)
    assert md.json_paths.radarr.quality_profiles == [
        "docs/json/radarr/quality-profiles"
    ]


def test_load_metadata_missing_raises(tmp_path):
    with pytest.raises(TrashError, match=r"metadata\.json not found"):
        load_metadata(tmp_path)
