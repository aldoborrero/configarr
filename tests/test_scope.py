import logging

from configarr.config import expand_env_vars, parse_config
from configarr.scope import in_scope


def test_in_scope_predicate():
    assert in_scope("radarr", "movies", None, None)
    assert in_scope("radarr", "movies", "RADARR", None)  # service case-insensitive
    assert not in_scope("radarr", "movies", "sonarr", None)
    assert in_scope("radarr", "movies", "radarr", "movies")
    assert not in_scope("radarr", "movies", "radarr", "anime")  # instance exact
    assert not in_scope("radarr", "movies", None, "anime")


def test_expand_env_vars_collects_unresolved(monkeypatch):
    monkeypatch.delenv("NOPE_VAR", raising=False)
    monkeypatch.setenv("SET_VAR", "value")
    unresolved: set[str] = set()
    out = expand_env_vars({"a": "${NOPE_VAR}", "b": "${SET_VAR}"}, unresolved)
    assert out["a"] == "${NOPE_VAR}"  # left literal
    assert out["b"] == "value"
    assert unresolved == {"NOPE_VAR"}


def test_parse_config_warns_on_unresolved_var(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        "radarr:\n  instances:\n    m:\n"
        "      base_url: http://r\n      api_key: ${MISSING_KEY}\n"
    )
    with caplog.at_level(logging.WARNING, logger="configarr.config"):
        parse_config(cfg)
    assert "unresolved" in caplog.text and "MISSING_KEY" in caplog.text
