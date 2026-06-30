import responses

from configarr.config import parse_config
from configarr.diff.runner import run_apply, run_plan

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

    assert "x265" in out or "custom formats" in out
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
