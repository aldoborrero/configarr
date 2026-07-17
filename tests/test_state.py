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
    # v2 stores name -> id (unknown ids are null), keys sorted.
    assert data["managed"]["radarr/movies"]["radarr.custom_format"] == {
        "A": None,
        "B": None,
    }


def test_id_recorded_and_preserved_across_set_managed(tmp_path):
    p = tmp_path / "state.json"
    s = State(p)
    s.set_managed("radarr/movies", "radarr.custom_format", ["A", "B"])
    s.set_id("radarr/movies", "radarr.custom_format", "A", 42)
    # Re-declaring the same keys keeps A's known id.
    s.set_managed("radarr/movies", "radarr.custom_format", ["A", "B"])
    s.save()
    loaded = State.load(p)
    assert loaded.managed_id("radarr/movies", "radarr.custom_format", "A") == 42
    assert loaded.managed_id("radarr/movies", "radarr.custom_format", "B") is None


def test_set_id_ignores_unmanaged_name(tmp_path):
    s = State(tmp_path / "s.json")
    s.set_managed("radarr/movies", "radarr.custom_format", ["A"])
    s.set_id("radarr/movies", "radarr.custom_format", "ghost", 9)
    assert s.managed_keys("radarr/movies", "radarr.custom_format") == {"A"}
    assert s.managed_id("radarr/movies", "radarr.custom_format", "ghost") is None


def test_loads_v1_list_shape(tmp_path):
    # A state file written by the previous (v1) release lists names without ids.
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "managed": {"radarr/movies": {"radarr.custom_format": ["A"]}},
            }
        )
    )
    s = State.load(p)
    assert s.managed_keys("radarr/movies", "radarr.custom_format") == {"A"}
    assert s.managed_id("radarr/movies", "radarr.custom_format", "A") is None


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
