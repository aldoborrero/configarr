import responses

from configarr.config import parse_config
from configarr.diff.runner import run_plan

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


MULTI_CONFIG_YAML = """
radarr:
  instances:
    main:
      base_url: http://main.test
      api_key: k
      custom_formats:
        definitions:
          x265:
            specifications:
              - name: x265
                implementation: ReleaseTitleSpecification
                fields:
                  value: "(x|h)265"
    uhd:
      base_url: http://uhd.test
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


def test_run_plan_no_radarr(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text("sonarr:\n  instances: {}\n")
    config = parse_config(cfg)
    assert run_plan(config) == "No supported resources configured for --plan."


def test_run_plan_service_filter_excludes_unconfigured_service(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    # No sonarr provider/instance exists, so filtering to it plans nothing
    # without touching the network.
    assert (
        run_plan(config, service="sonarr")
        == "No supported resources configured for --plan."
    )


@responses.activate
def test_run_plan_instance_filter_selects_only_that_instance(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(MULTI_CONFIG_YAML)
    config = parse_config(cfg)
    # Only register the selected instance's endpoints; if the runner queried the
    # other instance, responses would raise on an unmatched request.
    responses.get("http://main.test/api/v3/customformat", json=[])
    responses.get("http://main.test/api/v3/customformat/schema", json=SCHEMA)
    responses.get("http://main.test/api/v3/qualityprofile", json=[])
    responses.get("http://main.test/api/v3/qualitydefinition", json=[])
    responses.get("http://main.test/api/v3/config/naming", json={"id": 1})
    responses.get("http://main.test/api/v3/rootfolder", json=[])
    responses.get("http://main.test/api/v3/delayprofile", json=[])

    out = run_plan(config, instance="main")

    assert "main" in out and "uhd" not in out
    assert all("main.test" in c.request.url for c in responses.calls)


@responses.activate
def test_run_plan_reports_create_and_writes_nothing(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(CONFIG_YAML)
    config = parse_config(cfg)
    responses.get(f"{BASE}/api/v3/customformat", json=[])
    responses.get(f"{BASE}/api/v3/customformat/schema", json=SCHEMA)
    responses.get(f"{BASE}/api/v3/qualityprofile", json=[])
    responses.get(f"{BASE}/api/v3/qualitydefinition", json=[])
    responses.get(f"{BASE}/api/v3/config/naming", json={"id": 1})
    responses.get(f"{BASE}/api/v3/rootfolder", json=[])
    responses.get(f"{BASE}/api/v3/delayprofile", json=[])

    out = run_plan(config)

    assert "x265" in out and "create" in out.lower()
    assert all(c.request.method == "GET" for c in responses.calls)  # read-only
