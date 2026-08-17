import json
import logging

import pytest

from configarr.config import parse_config
from configarr.schema import build_json_schema, unknown_keys


def test_schema_structure_and_serializable():
    s = build_json_schema()
    assert s["type"] == "object"
    assert set(s["properties"]) == {
        "radarr",
        "sonarr",
        "prowlarr",
        "bazarr",
        "sabnzbd",
        "lingarr",
    }
    assert s["additionalProperties"] is False
    inst = s["properties"]["radarr"]["properties"]["instances"]["additionalProperties"]
    assert inst["required"] == ["base_url", "api_key"]
    assert inst["additionalProperties"] is False
    assert "custom_formats" in inst["properties"]
    # trash + include are embedded as $defs
    assert inst["properties"]["trash"] == {"$ref": "#/$defs/trash"}
    assert "trash" in s["$defs"]
    assert "include" in s["$defs"]
    json.dumps(s)  # must be JSON-serializable


def test_prowlarr_instance_sections():
    inst = build_json_schema()["properties"]["prowlarr"]["properties"]["instances"][
        "additionalProperties"
    ]
    assert set(inst["properties"]) >= {"indexers", "applications", "download_clients"}
    assert "custom_formats" not in inst["properties"]  # arr-only section


def test_unknown_keys_detects_section_typo():
    raw = {
        "radarr": {
            "instances": {"m": {"base_url": "x", "api_key": "k", "custom_format": {}}}
        }
    }
    assert unknown_keys(raw) == ["radarr.instances.m.custom_format"]


def test_unknown_keys_detects_nested_typo():
    raw = {
        "radarr": {
            "instances": {
                "m": {
                    "base_url": "x",
                    "api_key": "k",
                    "custom_formats": {"definition": {}},
                }
            }
        }
    }
    assert unknown_keys(raw) == ["radarr.instances.m.custom_formats.definition"]


def test_unknown_keys_clean_for_valid_config():
    raw = {
        "sabnzbd": {
            "instances": {
                "m": {"base_url": "x", "api_key": "k", "servers": {}, "misc": {}}
            }
        }
    }
    assert unknown_keys(raw) == []


def test_parse_config_warns_on_unknown_key(tmp_path, caplog):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      custom_format:\n        definitions: {}\n"
    )
    with caplog.at_level(logging.WARNING, logger="configarr.config"):
        parse_config(cfg)  # succeeds; the typo is only warned about
    assert "unrecognized config keys" in caplog.text
    assert "custom_format" in caplog.text


def test_parse_config_strict_raises_on_unknown_key(tmp_path):
    cfg = tmp_path / "configarr.yml"
    cfg.write_text(
        "radarr:\n  instances:\n    m:\n      base_url: http://r\n"
        "      api_key: k\n      nope: 1\n"
    )
    with pytest.raises(ValueError, match="unrecognized config keys"):
        parse_config(cfg, strict=True)
