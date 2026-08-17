import shutil
import subprocess

import pytest
from pydantic import ValidationError

from configarr.models import TrashConfig
from configarr.trash.errors import TrashError
from configarr.trash.source import resolve_source

# --- local source -----------------------------------------------------------


def test_absolute_path_returned_as_is(guide_root):
    trash = TrashConfig(source="local", path=str(guide_root))
    assert resolve_source(trash, guide_root.parent) == guide_root


def test_relative_path_resolves_against_base(guide_root):
    trash = TrashConfig(source="local", path="guide")
    assert resolve_source(trash, guide_root.parent) == guide_root


def test_nonexistent_dir_raises(tmp_path):
    trash = TrashConfig(source="local", path="does-not-exist")
    with pytest.raises(TrashError, match="not found"):
        resolve_source(trash, tmp_path)


# --- model validation -------------------------------------------------------


def test_model_local_requires_path():
    with pytest.raises(ValidationError, match="requires 'path'"):
        TrashConfig(source="local")


def test_model_rejects_url_with_local():
    with pytest.raises(ValidationError, match="only valid with trash source 'git'"):
        TrashConfig(source="local", path="x", url="http://x")


def test_model_rejects_path_with_git():
    with pytest.raises(ValidationError, match="only valid with trash source 'local'"):
        TrashConfig(source="git", url="http://x", path="x")


# --- git source -------------------------------------------------------------


def _make_remote(path, files, branch="main"):
    """Create a local git repo (a network-free stand-in for a remote Guides repo)."""
    subprocess.run(
        ["git", "init", "-b", branch, str(path)], check=True, capture_output=True
    )
    _commit(path, files, "init")
    return path


def _commit(path, files, message):
    for name, content in files.items():
        f = path / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content)
    subprocess.run(
        ["git", "-C", str(path), "add", "-A"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            message,
        ],
        check=True,
        capture_output=True,
    )


def test_git_clone_returns_cache_with_files(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    remote = _make_remote(
        tmp_path / "remote",
        {"metadata.json": "{}", "docs/json/radarr/cf/x.json": "{}"},
    )
    trash = TrashConfig(source="git", url=f"file://{remote}", ref="main")
    root = resolve_source(trash, tmp_path)
    assert (root / "metadata.json").is_file()
    assert (root / "docs/json/radarr/cf/x.json").is_file()
    # Cache lives under XDG_CACHE_HOME/configarr/guides.
    assert str(tmp_path / "cache") in str(root)


def test_git_default_branch_when_ref_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    remote = _make_remote(tmp_path / "remote", {"metadata.json": "{}"})
    trash = TrashConfig(source="git", url=f"file://{remote}")
    root = resolve_source(trash, tmp_path)
    assert (root / "metadata.json").is_file()


def test_git_ref_selects_branch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    remote = _make_remote(tmp_path / "remote", {"marker": "main"})
    subprocess.run(
        ["git", "-C", str(remote), "checkout", "-b", "other"],
        check=True,
        capture_output=True,
    )
    _commit(remote, {"marker": "other"}, "other")
    trash = TrashConfig(source="git", url=f"file://{remote}", ref="other")
    root = resolve_source(trash, tmp_path)
    assert (root / "marker").read_text() == "other"


def test_git_ref_accepts_commit_sha(tmp_path, monkeypatch):
    # A commit SHA is a documented `ref`, but `git clone --branch <sha>` rejects it.
    # Pinning must fetch that exact commit, not the branch tip.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    remote = _make_remote(tmp_path / "remote", {"marker": "first"})
    sha = subprocess.run(
        ["git", "-C", str(remote), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _commit(remote, {"marker": "second"}, "second")  # advance the branch past the pin
    trash = TrashConfig(source="git", url=f"file://{remote}", ref=sha)
    root = resolve_source(trash, tmp_path)
    assert (root / "marker").read_text() == "first"


def test_git_offline_falls_back_to_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    remote = _make_remote(tmp_path / "remote", {"metadata.json": "{}"})
    trash = TrashConfig(source="git", url=f"file://{remote}", ref="main")
    root1 = resolve_source(trash, tmp_path)  # clones
    shutil.rmtree(remote)  # remote vanishes -> the update fetch will fail
    root2 = resolve_source(trash, tmp_path)  # must reuse the cache, not raise
    assert root1 == root2
    assert (root2 / "metadata.json").is_file()


def test_git_missing_binary_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("configarr.trash.source.shutil.which", lambda _: None)
    trash = TrashConfig(source="git", url="file:///x", ref="main")
    with pytest.raises(TrashError, match="requires the 'git'"):
        resolve_source(trash, tmp_path)


def test_git_bad_url_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    trash = TrashConfig(source="git", url=f"file://{tmp_path}/nope", ref="main")
    with pytest.raises(TrashError, match="git clone"):
        resolve_source(trash, tmp_path)
