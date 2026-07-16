"""CLI-level tests for the Click entrypoint: exit codes and flag validation that
run *before* any HTTP, so no mocking is needed."""

from click.testing import CliRunner

from configarr.__main__ import main

VALID = """
radarr:
  instances:
    movies:
      base_url: http://r.test
      api_key: k
"""


def _write(tmp_path, text):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(text)
    return str(cfg)


def test_output_json_without_plan_exits_2(tmp_path):
    cfg = _write(tmp_path, VALID)
    res = CliRunner().invoke(main, ["--config", cfg, "--output", "json"])
    assert res.exit_code == 2
    assert "--output json requires --plan" in res.output


def test_unknown_service_with_no_instances_exits_2(tmp_path):
    cfg = _write(tmp_path, VALID)
    res = CliRunner().invoke(main, ["--config", cfg, "--service", "sonarr", "--plan"])
    assert res.exit_code == 2
    assert "No 'sonarr' instances" in res.output


def test_unknown_instance_exits_2(tmp_path):
    cfg = _write(tmp_path, VALID)
    res = CliRunner().invoke(main, ["--config", cfg, "--instance", "nope", "--plan"])
    assert res.exit_code == 2
    assert "No instance named 'nope'" in res.output


def test_invalid_config_exits_1(tmp_path):
    # radarr instance missing the required api_key -> Pydantic ValidationError.
    cfg = _write(
        tmp_path, "radarr:\n  instances:\n    movies:\n      base_url: http://r\n"
    )
    res = CliRunner().invoke(main, ["--config", cfg, "--plan"])
    assert res.exit_code == 1
    assert "Configuration error" in res.output


def test_malformed_yaml_exits_1(tmp_path):
    cfg = _write(tmp_path, "radarr: [unclosed\n")
    res = CliRunner().invoke(main, ["--config", cfg, "--plan"])
    assert res.exit_code == 1
    assert "Invalid YAML" in res.output


def test_missing_config_file_is_rejected(tmp_path):
    # Click's Path(exists=True) guards this before main runs (usage error, exit 2).
    res = CliRunner().invoke(main, ["--config", str(tmp_path / "nope.yml"), "--plan"])
    assert res.exit_code == 2


def test_check_valid_config_exits_0_without_network(tmp_path):
    # The base_url points at a host that isn't there; --check must succeed anyway,
    # proving it validates offline and never contacts the service.
    cfg = _write(tmp_path, VALID)
    res = CliRunner().invoke(main, ["--config", cfg, "--check"])
    assert res.exit_code == 0
    assert "OK" in res.output
    assert "1 instance(s)" in res.output


def test_check_invalid_config_exits_1(tmp_path):
    cfg = _write(
        tmp_path, "radarr:\n  instances:\n    movies:\n      base_url: http://r\n"
    )
    res = CliRunner().invoke(main, ["--config", cfg, "--check"])
    assert res.exit_code == 1
    assert "Configuration error" in res.output


def test_check_validates_trash_resolvability(tmp_path):
    # A trash block whose local guide path does not exist must fail --check, so a
    # broken TRaSH import is caught in CI before an apply ever runs.
    cfg = _write(
        tmp_path,
        "radarr:\n  instances:\n    movies:\n"
        "      base_url: http://r.test\n      api_key: k\n"
        "      trash:\n        source: local\n        path: /nonexistent/guides\n"
        "        quality_definition: movie\n",
    )
    res = CliRunner().invoke(main, ["--config", cfg, "--check"])
    assert res.exit_code == 1
    assert "TRaSH import error" in res.output
