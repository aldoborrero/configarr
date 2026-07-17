import json

from configarr.state import STATE_VERSION, State


def test_empty_when_file_absent(tmp_path):
    s = State.load(tmp_path / "nope.json")
    assert s.managed_keys("radarr/movies", "radarr.custom_format") == set()


def test_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.set_managed("radarr/movies", "radarr.custom_format", ["A", "B"])
    s.save()
    loaded = State.load(p)
    assert loaded.managed_keys("radarr/movies", "radarr.custom_format") == {"A", "B"}


def test_save_is_versioned_and_sorted(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.set_managed("radarr/movies", "radarr.custom_format", ["B", "A"])
    s.save()
    data = json.loads(p.read_text())
    assert data["version"] == STATE_VERSION
    assert data["managed"]["radarr/movies"]["radarr.custom_format"] == ["A", "B"]


def test_set_empty_drops_scope(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.set_managed("radarr/movies", "radarr.custom_format", ["A"])
    s.set_managed("radarr/movies", "radarr.custom_format", [])
    s.save()
    assert json.loads(p.read_text())["managed"] == {}


def test_unreadable_file_is_empty(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not json")
    s = State.load(p)
    assert s.managed_keys("radarr/movies", "radarr.custom_format") == set()


def test_scopes_and_kinds_are_isolated(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_managed("radarr/movies", "radarr.custom_format", ["A"])
    s.set_managed("sonarr/tv", "sonarr.custom_format", ["B"])
    assert s.managed_keys("radarr/movies", "radarr.custom_format") == {"A"}
    assert s.managed_keys("sonarr/tv", "sonarr.custom_format") == {"B"}
    assert s.managed_keys("radarr/movies", "sonarr.custom_format") == set()


def test_save_atomic_leaves_no_tmp(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.set_managed("radarr/movies", "radarr.custom_format", ["A"])
    s.save()
    assert p.is_file()
    assert not (tmp_path / "state.json.tmp").exists()
