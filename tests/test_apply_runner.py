import responses

from configarr import runner
from configarr.config import parse_config
from configarr.model import Op
from configarr.providers.base import Action
from configarr.registry import PlannedProvider
from configarr.runner import run_apply, run_plan
from configarr.state import State

CONFIG_NO_CF = """
radarr:
  instances:
    main:
      base_url: http://radarr.test
      api_key: k
"""

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

CONFIG_YAML = """
radarr:
  instances:
    main:
      base_url: http://radarr.test
      api_key: k
      custom_formats:
        definitions:
          x265:
            specifications:
              - name: x265
                implementation: ReleaseTitleSpecification
                fields:
                  value: "(x|h)265"
"""

CREATED = {
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


def _register_radarr_reads(custom_formats):
    responses.get(f"{BASE}/api/v3/customformat", json=custom_formats)
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=[])
    responses.get(f"{BASE}/api/v3/config/naming", json={"id": 1})
    responses.get(f"{BASE}/api/v3/rootfolder", json=[])
    responses.get(f"{BASE}/api/v3/delayprofile", json=[])
    responses.get(f"{BASE}/api/v3/downloadclient", json=[])
    responses.get(f"{BASE}/api/v3/notification", json=[])


class _CountingProvider:
    """Minimal provider that counts build_desired/fetch_current calls so the apply
    path's single-build guarantee can be asserted directly."""

    kind = "fake"
    full_replace = False
    prunable = False

    def __init__(self):
        self.build_calls = 0
        self.fetch_calls = 0
        self.applied: list[Action] = []

    def fetch_current(self):
        self.fetch_calls += 1
        return []

    def build_desired(self):
        self.build_calls += 1
        return [{"name": "x"}]

    def match_key(self, resource):
        return resource.get("name")

    def normalize(self, resource):
        return resource

    def to_action(self, plan, current, desired):
        return Action(op=plan.op, key=plan.key, payload=desired or {})

    def apply(self, action):
        self.applied.append(action)


def test_run_apply_builds_desired_once(monkeypatch):
    # The apply path must compute desired ONCE and derive both the plan and the
    # action payloads from it; a second build_desired() could observe drifted state
    # (TOCTOU) between planning and applying.
    provider = _CountingProvider()
    planned = PlannedProvider(
        service="radarr", instance="main", label="fake", provider=provider
    )
    monkeypatch.setattr(runner, "providers_for", lambda *a, **k: [planned])

    run_apply(config=None)

    assert provider.build_calls == 1
    assert [a.op for a in provider.applied] == [Op.CREATE]


def test_run_apply_no_changes(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text("sonarr:\n  instances: {}\n")
    config = parse_config(cfg)
    assert run_apply(config) == "No changes to apply."


@responses.activate
def test_run_apply_creates_and_writes(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)

    out = run_apply(config)

    assert "custom formats: applied 1 change(s)" in out
    posts = [c for c in responses.calls if c.request.method == "POST"]
    assert len(posts) == 1
    assert posts[0].request.url == f"{BASE}/api/v3/customformat"


@responses.activate
def test_run_apply_prune_deletes_only_unmanaged(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    # Server already has the managed CF plus an unmanaged leftover.
    _register_radarr_reads([CREATED, {**CREATED, "id": 99, "name": "stale"}])
    responses.delete(f"{BASE}/api/v3/customformat/99", status=200)

    out = run_apply(config, prune=True)

    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].request.url == f"{BASE}/api/v3/customformat/99"
    assert "custom formats" in out

    # Re-plan with prune: the managed CF stays, stale is gone, nothing to do.
    responses.reset()
    _register_radarr_reads([CREATED])
    assert run_apply(config, prune=True) == "No changes to apply."


@responses.activate
def test_run_apply_without_prune_never_deletes(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    _register_radarr_reads([CREATED, {**CREATED, "id": 99, "name": "stale"}])

    out = run_apply(config)

    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert deletes == []
    assert out == "No changes to apply."


@responses.activate
def test_run_apply_then_replan_is_empty(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)

    run_apply(config)

    # Server now returns the created custom format; a fresh plan must be empty.
    responses.reset()
    _register_radarr_reads([CREATED])
    out = run_plan(config)
    assert "create" not in out.lower()
    assert "update" not in out.lower()


@responses.activate
def test_run_apply_surfaces_partial_state_on_failure(tmp_path):
    # A mid-run write failure must not be silent about what was already applied.
    import pytest

    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", status=500)
    with pytest.raises(RuntimeError, match="apply aborted"):
        run_apply(config)


@responses.activate
def test_prune_with_state_spares_unmanaged(tmp_path):
    # With ownership state, a CF configarr never created is NOT pruned even though
    # it's absent from config — the legacy path (no state) would delete it.
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    sp = tmp_path / ".configarr-state.json"
    _register_radarr_reads([CREATED, {**CREATED, "id": 99, "name": "userCF"}])

    run_apply(config, prune=True, state_path=sp)

    assert [c for c in responses.calls if c.request.method == "DELETE"] == []
    # x265 is recorded as managed; the user's CF is not.
    assert State.load(sp).managed_keys("radarr/main", "radarr.custom_format") == {
        "x265"
    }


@responses.activate
def test_prune_with_state_deletes_dropped_managed_cf(tmp_path):
    sp = tmp_path / ".configarr-state.json"
    # Run 1: config declares x265 -> created and recorded as managed.
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)
    run_apply(parse_config(cfg), state_path=sp)
    assert State.load(sp).managed_keys("radarr/main", "radarr.custom_format") == {
        "x265"
    }

    # Run 2: config drops x265; the server still has it; prune deletes it because
    # it is configarr-managed, and state is updated to forget it.
    responses.reset()
    cfg.write_text(CONFIG_NO_CF)
    _register_radarr_reads([CREATED])
    responses.delete(f"{BASE}/api/v3/customformat/7", status=200)
    run_apply(parse_config(cfg), prune=True, state_path=sp)

    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].request.url == f"{BASE}/api/v3/customformat/7"
    assert State.load(sp).managed_keys("radarr/main", "radarr.custom_format") == set()


@responses.activate
def test_state_records_managed_even_when_unchanged(tmp_path):
    sp = tmp_path / ".configarr-state.json"
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    _register_radarr_reads([CREATED])  # already matches config -> no change

    assert run_apply(parse_config(cfg), state_path=sp) == "No changes to apply."
    assert sp.is_file()
    assert State.load(sp).managed_keys("radarr/main", "radarr.custom_format") == {
        "x265"
    }


@responses.activate
def test_rename_tolerant_matching_updates_in_place(tmp_path):
    # A managed CF renamed on the server (id unchanged) is updated in place — renamed
    # back to match config — not duplicated.
    sp = tmp_path / ".configarr-state.json"
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)

    # Run 1: create x265 (id 7) and record its id in state.
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)
    run_apply(parse_config(cfg), state_path=sp)
    assert State.load(sp).managed_id("radarr/main", "radarr.custom_format", "x265") == 7

    # Run 2: a user renamed id 7 to "x265-renamed"; config still declares "x265".
    responses.reset()
    _register_radarr_reads([{**CREATED, "name": "x265-renamed"}])
    responses.put(f"{BASE}/api/v3/customformat/7", json=CREATED, status=200)
    run_apply(parse_config(cfg), state_path=sp)

    assert [c for c in responses.calls if c.request.method == "POST"] == []
    puts = [c for c in responses.calls if c.request.method == "PUT"]
    assert len(puts) == 1
    assert puts[0].request.url == f"{BASE}/api/v3/customformat/7"


@responses.activate
def test_rename_tolerant_matching_no_dup_when_id_gone(tmp_path):
    # If the recorded id no longer exists (user deleted it), fall back to a normal
    # create — no spurious update against a missing id.
    sp = tmp_path / ".configarr-state.json"
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    _register_radarr_reads([])
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)
    run_apply(parse_config(cfg), state_path=sp)

    responses.reset()
    _register_radarr_reads([])  # id 7 is gone from the server
    responses.post(f"{BASE}/api/v3/customformat", json=CREATED, status=201)
    run_apply(parse_config(cfg), state_path=sp)
    assert len([c for c in responses.calls if c.request.method == "POST"]) == 1
