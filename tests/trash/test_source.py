import pytest

from configarr.models import TrashConfig
from configarr.trash.errors import TrashError
from configarr.trash.source import resolve_source


def test_absolute_path_returned_as_is(guide_root):
    trash = TrashConfig(source="local", path=str(guide_root))
    assert resolve_source(trash, guide_root.parent) == guide_root


def test_relative_path_resolves_against_base(guide_root):
    trash = TrashConfig(source="local", path="guide")
    assert resolve_source(trash, guide_root.parent) == guide_root


def test_missing_path_raises(tmp_path):
    trash = TrashConfig(source="local", path=None)
    with pytest.raises(TrashError, match="requires a 'path'"):
        resolve_source(trash, tmp_path)


def test_nonexistent_dir_raises(tmp_path):
    trash = TrashConfig(source="local", path="does-not-exist")
    with pytest.raises(TrashError, match="not found"):
        resolve_source(trash, tmp_path)
