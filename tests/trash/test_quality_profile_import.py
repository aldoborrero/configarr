"""Full TRaSH quality-profile import: a whole guide profile by trash_id, pulling
its custom formats + scores + custom quality grouping into the instance."""

import pytest
import responses

from configarr.models import ArrServiceConfig, ConfigarrConfig, TrashConfig
from configarr.providers.arr.quality_profiles import QualityProfileProvider
from configarr.trash import resolve_trash
from configarr.trash.catalog import Catalog
from configarr.trash.errors import TrashError
from configarr.trash.metadata import load_metadata


def _instance(guide_root, **trash):
    return ArrServiceConfig(
        name="movies",
        base_url="http://r.test",
        api_key="k",
        trash=TrashConfig(source="local", path=str(guide_root), **trash),
    )


def _resolve(guide_root, inst):
    resolve_trash(ConfigarrConfig(radarr=[inst]), guide_root.parent)


# ---- catalog ----------------------------------------------------------------


def test_catalog_loads_quality_profile(guide_root):
    catalog = Catalog(guide_root, load_metadata(guide_root).json_paths.radarr)
    qp = catalog.quality_profile("qp-hd-web")
    assert qp["name"] == "HD WEB"
    assert qp["score_set"] == "default"
    assert qp["cutoff"] == "1080p WEB"
    assert qp["format_items"] == {"HDR10": "aaa111", "Dual Audio": "bbb222"}
    assert qp["items"][0]["items"] == ["WEBDL-1080p", "WEBRip-1080p"]


def test_catalog_unknown_profile_raises(guide_root):
    catalog = Catalog(guide_root, load_metadata(guide_root).json_paths.radarr)
    with pytest.raises(TrashError, match="quality profile trash_id not found"):
        catalog.quality_profile("nope")


# ---- resolver ---------------------------------------------------------------


def test_imports_profile_with_grouping_and_scores(guide_root):
    inst = _instance(guide_root, quality_profiles=[{"trash_id": "qp-hd-web"}])
    _resolve(guide_root, inst)

    # The custom formats the profile scores were imported.
    assert "HDR10" in inst.custom_formats
    assert "Dual Audio" in inst.custom_formats

    [prof] = inst.quality_profiles
    assert prof["name"] == "HD WEB"
    assert prof["upgrade"] == {
        "allowed": True,
        "until_quality": "1080p WEB",
        "until_score": 10000,
    }
    assert prof["language"] == "Original"
    # Enabled entries, in order; the custom group preserved, SDTV (disabled) dropped.
    assert prof["qualities"] == [
        {"name": "1080p WEB", "qualities": ["WEBDL-1080p", "WEBRip-1080p"]},
        "Bluray-1080p",
    ]
    # Scores from the 'default' set: HDR10=100, Dual Audio=0.
    assert prof["custom_format_scores"] == {"HDR10": 100, "Dual Audio": 0}


def test_name_override(guide_root):
    inst = _instance(
        guide_root,
        quality_profiles=[{"trash_id": "qp-hd-web", "name": "My HD"}],
    )
    _resolve(guide_root, inst)
    assert inst.quality_profiles[0]["name"] == "My HD"


def test_score_set_override(guide_root):
    # bbb222 (Dual Audio) has french-multi=1500; overriding the score set uses it.
    inst = _instance(
        guide_root,
        quality_profiles=[{"trash_id": "qp-hd-web", "score_set": "french-multi"}],
    )
    _resolve(guide_root, inst)
    scores = inst.quality_profiles[0]["custom_format_scores"]
    assert scores["Dual Audio"] == 1500  # from french-multi
    assert scores["HDR10"] == 100  # aaa111 has no french-multi -> default 100


def test_merges_into_user_defined_profile(guide_root):
    # A same-named profile you define keeps its structure and its own scores, and
    # the guide's custom formats + scores are layered in (recyclarr include+override).
    inst = _instance(guide_root, quality_profiles=[{"trash_id": "qp-hd-web"}])
    inst.quality_profiles.append(
        {
            "name": "HD WEB",
            "qualities": ["Bluray-1080p"],
            "custom_format_scores": {"HDR10": 999},  # your score
        }
    )
    _resolve(guide_root, inst)

    hd = [p for p in inst.quality_profiles if p["name"] == "HD WEB"]
    assert len(hd) == 1
    assert hd[0]["qualities"] == ["Bluray-1080p"]  # structure untouched
    # Your HDR10 score wins; the guide's other CF (Dual Audio) is merged in.
    assert hd[0]["custom_format_scores"]["HDR10"] == 999
    assert hd[0]["custom_format_scores"]["Dual Audio"] == 0
    # ...and the guide's custom formats were imported.
    assert "HDR10" in inst.custom_formats
    assert "Dual Audio" in inst.custom_formats


# ---- end-to-end through the real provider -----------------------------------

SCHEMA = {
    "name": "",
    "upgradeAllowed": False,
    "cutoff": 1,
    "items": [
        {"quality": {"id": 1, "name": "SDTV"}, "items": [], "allowed": False},
        {"quality": {"id": 2, "name": "WEBDL-1080p"}, "items": [], "allowed": False},
        {"quality": {"id": 3, "name": "WEBRip-1080p"}, "items": [], "allowed": False},
        {"quality": {"id": 4, "name": "Bluray-1080p"}, "items": [], "allowed": False},
    ],
    "minFormatScore": 0,
    "cutoffFormatScore": 0,
    "minUpgradeFormatScore": 1,
    "formatItems": [
        {"format": 10, "name": "HDR10", "score": 0},
        {"format": 11, "name": "Dual Audio", "score": 0},
    ],
    "language": {"id": 1, "name": "Any"},
}


@responses.activate
def test_imported_profile_builds_valid_grouped_payload(guide_root):
    inst = _instance(guide_root, quality_profiles=[{"trash_id": "qp-hd-web"}])
    _resolve(guide_root, inst)

    responses.get("http://r.test/api/v3/qualityprofile", json=[])
    responses.get("http://r.test/api/v3/qualityprofile/schema", json=SCHEMA)
    responses.get(
        "http://r.test/api/v3/language", json=[{"id": -2, "name": "Original"}]
    )
    provider = QualityProfileProvider(
        "http://r.test", "k", inst.quality_profiles, "radarr.quality_profile"
    )
    [desired] = provider.build_desired()

    group = desired["items"][0]
    assert group["name"] == "1080p WEB"
    assert group["allowed"] is True
    assert [c["quality"]["name"] for c in group["items"]] == [
        "WEBDL-1080p",
        "WEBRip-1080p",
    ]
    assert desired["items"][1]["quality"]["name"] == "Bluray-1080p"
    # SDTV unlisted -> disabled at the bottom.
    assert desired["items"][-1]["quality"]["name"] == "SDTV"
    assert desired["items"][-1]["allowed"] is False
    # Cutoff resolves to the custom group's id; language + scores applied.
    assert desired["cutoff"] == group["id"]
    assert desired["language"] == {"id": -2, "name": "Original"}
    scores = {fi["name"]: fi["score"] for fi in desired["formatItems"]}
    assert scores == {"HDR10": 100, "Dual Audio": 0}
