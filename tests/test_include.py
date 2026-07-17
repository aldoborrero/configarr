import pytest

from configarr.config import parse_config


def _write(directory, name, text):
    p = directory / name
    p.write_text(text)
    return p


def _main(directory, body):
    return _write(directory, "configarr.yml", body)


def test_include_merges_shared_and_instance_wins(tmp_path):
    _write(
        tmp_path,
        "shared.yml",
        "base_url: http://shared\napi_key: shared-key\n"
        "custom_formats:\n  definitions:\n    Shared: {}\n",
    )
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    movies:\n"
        "      base_url: http://own\n      include: [shared.yml]\n"
        "      custom_formats:\n        definitions:\n          Own: {}\n",
    )
    inst = parse_config(cfg).radarr[0]
    assert inst.base_url == "http://own"  # instance overrides the include
    assert inst.api_key == "shared-key"  # inherited from the include
    assert set(inst.custom_formats) == {"Shared", "Own"}  # maps are unioned


def test_multiple_includes_merge_in_order(tmp_path):
    _write(
        tmp_path, "a.yml", "api_key: k\ncustom_formats:\n  definitions:\n    A: {}\n"
    )
    _write(
        tmp_path,
        "b.yml",
        "custom_formats:\n  definitions:\n    B: {}\n",
    )
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      include: [a.yml, b.yml]\n",
    )
    inst = parse_config(cfg).radarr[0]
    assert set(inst.custom_formats) == {"A", "B"}
    assert inst.api_key == "k"


def test_include_config_mapping_form(tmp_path):
    _write(tmp_path, "s.yml", "api_key: k\n")
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      include:\n        - config: s.yml\n",
    )
    assert parse_config(cfg).radarr[0].api_key == "k"


def test_nested_include(tmp_path):
    _write(tmp_path, "leaf.yml", "custom_formats:\n  definitions:\n    Leaf: {}\n")
    _write(
        tmp_path,
        "mid.yml",
        "api_key: k\ninclude: [leaf.yml]\n"
        "custom_formats:\n  definitions:\n    Mid: {}\n",
    )
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      include: [mid.yml]\n",
    )
    inst = parse_config(cfg).radarr[0]
    assert set(inst.custom_formats) == {"Leaf", "Mid"}


def test_included_env_vars_are_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("SHARED_KEY", "from-env")
    _write(tmp_path, "s.yml", "api_key: ${SHARED_KEY}\n")
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      include: [s.yml]\n",
    )
    assert parse_config(cfg).radarr[0].api_key == "from-env"


def test_missing_include_raises(tmp_path):
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      include: [nope.yml]\n",
    )
    with pytest.raises(ValueError, match="include file not found"):
        parse_config(cfg)


def test_non_mapping_include_raises(tmp_path):
    _write(tmp_path, "bad.yml", "- just\n- a list\n")
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      include: [bad.yml]\n",
    )
    with pytest.raises(ValueError, match="must be a YAML mapping"):
        parse_config(cfg)


def test_include_cycle_raises(tmp_path):
    _write(tmp_path, "x.yml", "include: [y.yml]\n")
    _write(tmp_path, "y.yml", "include: [x.yml]\n")
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      include: [x.yml]\n",
    )
    with pytest.raises(ValueError, match="cycle"):
        parse_config(cfg)


def test_bad_include_entry_raises(tmp_path):
    cfg = _main(
        tmp_path,
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      include: [123]\n",
    )
    with pytest.raises(ValueError, match="invalid include entry"):
        parse_config(cfg)
