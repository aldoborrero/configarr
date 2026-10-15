from configarr.providers.cleanuparr.common import (
    camelize,
    flatten,
    merge_over,
    to_wire,
)


def test_camelize():
    assert camelize("failed_import_max_strikes") == "failedImportMaxStrikes"
    assert camelize("dryRun") == "dryRun"


def test_merge_maps_onto_server_spelling():
    current = {"log": {"rollingSizeMB": 10, "level": "Information"}}
    merged = merge_over(current, {"log": {"rolling_size_mb": 20}})
    # Lands on the server's own key, not a new "rollingSizeMb".
    assert merged == {"log": {"rollingSizeMB": 20, "level": "Information"}}


def test_merge_keeps_server_enum_spelling():
    merged = merge_over({"patternMode": "Exclude"}, {"pattern_mode": "exclude"})
    assert merged == {"patternMode": "Exclude"}


def test_merge_unknown_key_falls_back_to_camel_case():
    assert merge_over({}, {"new_setting": 1}) == {"newSetting": 1}


def test_to_wire_camelizes_nested():
    assert to_wire({"a_b": {"c_d": [{"e_f": 1}]}}) == {"aB": {"cD": [{"eF": 1}]}}


def test_flatten_uses_dotted_paths_and_coerces():
    assert flatten({"a": {"b": "3", "c": [1]}, "d": True}) == {
        "a.b": 3,
        "a.c": [1],
        "d": True,
    }
