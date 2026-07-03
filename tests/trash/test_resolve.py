import pytest

from configarr.models import ArrServiceConfig, ConfigarrConfig, TrashConfig
from configarr.trash import resolve_trash
from configarr.trash.errors import TrashError


def _instance(guide_root, **trash):
    return ArrServiceConfig(
        name="movies",
        base_url="http://r.test",
        api_key="k",
        quality_profiles=[{"name": "HD", "custom_format_scores": {}}],
        trash=TrashConfig(source="local", path=str(guide_root), **trash),
    )


def _resolve(guide_root, inst):
    resolve_trash(ConfigarrConfig(radarr=[inst]), guide_root.parent)


def test_imports_custom_formats_into_instance(guide_root):
    inst = _instance(guide_root, custom_formats=[{"trash_ids": ["aaa111", "bbb222"]}])
    _resolve(guide_root, inst)
    assert set(inst.custom_formats) == {"HDR10", "Dual Audio"}
    assert inst.custom_formats["HDR10"]["specifications"][0]["fields"] == {
        "value": "\\bHDR10\\b"
    }
    assert inst.custom_formats["Dual Audio"]["include_when_renaming"] is True


def test_assigns_default_score_to_named_profile(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {"trash_ids": ["aaa111"], "assign_scores_to": [{"profile": "HD"}]}
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["HDR10"] == 100


def test_score_set_selects_named_set(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {
                "trash_ids": ["bbb222"],
                "assign_scores_to": [{"profile": "HD", "score_set": "french-multi"}],
            }
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["Dual Audio"] == 1500


def test_explicit_score_overrides_guide(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {
                "trash_ids": ["aaa111"],
                "assign_scores_to": [{"profile": "HD", "score": -50}],
            }
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["HDR10"] == -50


def test_missing_score_set_defaults_to_zero(guide_root):
    # ccc333 has only the 'sqp' set, no 'default'.
    inst = _instance(
        guide_root,
        custom_formats=[
            {"trash_ids": ["ccc333"], "assign_scores_to": [{"profile": "HD"}]}
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["Legacy Array Fields"] == 0


def test_missing_named_score_set_falls_back_to_default(guide_root):
    # aaa111 has only 'default': 100; a missing named set falls back to it (100),
    # not 0 — matching recyclarr.
    inst = _instance(
        guide_root,
        custom_formats=[
            {
                "trash_ids": ["aaa111"],
                "assign_scores_to": [{"profile": "HD", "score_set": "german"}],
            }
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["HDR10"] == 100


def test_score_set_matched_case_insensitively(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {
                "trash_ids": ["bbb222"],
                "assign_scores_to": [{"profile": "HD", "score_set": "FRENCH-MULTI"}],
            }
        ],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["Dual Audio"] == 1500


def test_resolve_skips_out_of_scope_service(guide_root):
    # A radarr instance with a broken path must be skipped (not read, not raised)
    # when only sonarr is in scope.
    inst = ArrServiceConfig(
        name="movies",
        base_url="http://r.test",
        api_key="k",
        trash=TrashConfig(
            source="local",
            path="/nonexistent",
            custom_formats=[{"trash_ids": ["aaa111"]}],
        ),
    )
    resolve_trash(ConfigarrConfig(radarr=[inst]), guide_root.parent, service="sonarr")
    assert inst.custom_formats == {}


def test_resolve_skips_out_of_scope_instance(guide_root):
    good = _instance(guide_root, custom_formats=[{"trash_ids": ["aaa111"]}])  # "movies"
    bad = ArrServiceConfig(
        name="skip",
        base_url="http://r.test",
        api_key="k",
        trash=TrashConfig(
            source="local",
            path="/nonexistent",
            custom_formats=[{"trash_ids": ["aaa111"]}],
        ),
    )
    resolve_trash(
        ConfigarrConfig(radarr=[good, bad]), guide_root.parent, instance="movies"
    )
    assert "HDR10" in good.custom_formats
    assert bad.custom_formats == {}


def test_quality_definition_imported(guide_root):
    inst = _instance(guide_root, quality_definition="movie")
    _resolve(guide_root, inst)
    assert inst.quality_definitions["SDTV"] == {"min": 2, "max": 100, "preferred": 95}


def test_user_custom_format_wins(guide_root):
    inst = _instance(guide_root, custom_formats=[{"trash_ids": ["aaa111"]}])
    inst.custom_formats["HDR10"] = {"specifications": [], "include_when_renaming": True}
    _resolve(guide_root, inst)
    assert inst.custom_formats["HDR10"] == {
        "specifications": [],
        "include_when_renaming": True,
    }


def test_user_score_wins(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {"trash_ids": ["aaa111"], "assign_scores_to": [{"profile": "HD"}]}
        ],
    )
    inst.quality_profiles[0]["custom_format_scores"]["HDR10"] = 999
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["custom_format_scores"]["HDR10"] == 999


def test_user_quality_definition_wins(guide_root):
    inst = _instance(guide_root, quality_definition="movie")
    inst.quality_definitions = {"SDTV": {"min": 99}}
    _resolve(guide_root, inst)
    assert inst.quality_definitions["SDTV"] == {"min": 99}
    # Non-conflicting qualities are still imported.
    assert inst.quality_definitions["Bluray-1080p"] == {
        "min": 5,
        "max": 200,
        "preferred": 190,
    }


def test_unknown_trash_id_raises(guide_root):
    inst = _instance(guide_root, custom_formats=[{"trash_ids": ["zzz"]}])
    with pytest.raises(TrashError):
        _resolve(guide_root, inst)


def test_missing_profile_warns_but_still_imports_cf(guide_root):
    inst = _instance(
        guide_root,
        custom_formats=[
            {"trash_ids": ["aaa111"], "assign_scores_to": [{"profile": "Nope"}]}
        ],
    )
    _resolve(guide_root, inst)
    assert "HDR10" in inst.custom_formats  # imported despite the missing profile


def test_sonarr_instance_uses_sonarr_catalog(guide_root):
    inst = ArrServiceConfig(
        name="tv",
        base_url="http://s.test",
        api_key="k",
        trash=TrashConfig(
            source="local",
            path=str(guide_root),
            custom_formats=[{"trash_ids": ["sonarr999"]}],
        ),
    )
    resolve_trash(ConfigarrConfig(sonarr=[inst]), guide_root.parent)
    assert "Sonarr x265" in inst.custom_formats
