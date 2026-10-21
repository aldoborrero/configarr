"""Bookshelf wiring: config parsing, registry, and the shared arr providers running
against the Readarr ``/api/v1`` paths."""

import json

import pytest
import responses

from configarr.config import parse_config
from configarr.models import BookshelfConfig, ConfigarrConfig
from configarr.plan import Op
from configarr.providers.prowlarr.applications import ApplicationProvider
from configarr.registry import providers_for

BOOKSHELF = "http://bookshelf.test"
API = f"{BOOKSHELF}/api/v1"

CONFIG_YAML = """
bookshelf:
  instances:
    main:
      base_url: http://bookshelf.test/
      api_key: k
      custom_formats:
        definitions:
          Retail: {specifications: []}
      settings:
        media_management:
          rename_books: true
          colon_replacement: smart
        root_folders:
          - name: Libros
            path: /hdd/books
            default_quality_profile: eBook
            default_metadata_profile: Standard
      profiles:
        quality_profiles:
          definitions:
            eBook:
              upgrade_until_quality: EPUB
              qualities: [EPUB, AZW3, MOBI]
        metadata_profiles:
          definitions:
            Standard: {min_popularity: 0, allowed_languages: [spa, eng]}
        delay_profiles:
          - usenet_delay: 60
      download_clients:
        definitions:
          SABnzbd:
            implementation: Sabnzbd
            settings: {host: sabnzbd, musicCategory: books}
"""


def _parse(tmp_path, body=CONFIG_YAML):
    path = tmp_path / "configarr.yml"
    path.write_text(body)
    return parse_config(path, strict=True)


def test_parse_maps_every_section(tmp_path):
    [inst] = _parse(tmp_path).bookshelf
    assert inst.base_url == BOOKSHELF
    assert inst.custom_formats == {"Retail": {"specifications": []}}
    assert inst.naming_config == {"rename_books": True, "colon_replacement": "smart"}
    assert inst.root_folders[0]["default_metadata_profile"] == "Standard"
    assert inst.quality_profiles[0]["name"] == "eBook"
    assert inst.quality_profiles[0]["upgrade"]["until_quality"] == "EPUB"
    assert inst.metadata_profiles == {
        "Standard": {"min_popularity": 0, "allowed_languages": ["spa", "eng"]}
    }
    assert inst.delay_profiles == [{"usenet_delay": 60}]
    assert set(inst.download_clients) == {"SABnzbd"}


def test_trash_block_is_rejected(tmp_path):
    body = CONFIG_YAML.replace(
        "      api_key: k\n", "      api_key: k\n      trash: {source: git}\n"
    )
    with pytest.raises(ValueError, match="not available for Bookshelf"):
        parse_config(_write(tmp_path, body))


def _write(directory, body):
    path = directory / "configarr.yml"
    path.write_text(body)
    return path


def test_registry_orders_profiles_before_root_folders(tmp_path):
    planned = list(providers_for(_parse(tmp_path), service="bookshelf"))
    kinds = [p.provider.kind for p in planned]
    assert kinds == [
        "bookshelf.custom_format",
        "bookshelf.quality_profile",
        "bookshelf.metadata_profile",
        "bookshelf.root_folder",
        "bookshelf.naming",
        "bookshelf.delay_profile",
        "bookshelf.download_client",
    ]
    assert all(getattr(p.provider, "api_prefix", None) == "/api/v1" for p in planned)


def test_bookshelf_does_not_leak_into_radarr():
    config = ConfigarrConfig(
        bookshelf=[BookshelfConfig(name="main", base_url=BOOKSHELF, api_key="k")]
    )
    planned = list(providers_for(config))
    assert {p.service for p in planned} == {"bookshelf"}


def _provider(tmp_path, kind):
    for planned in providers_for(_parse(tmp_path), service="bookshelf"):
        if planned.provider.kind == kind:
            return planned.provider
    raise AssertionError(kind)


@responses.activate
def test_naming_uses_readarr_fields(tmp_path, plan_provider, apply_changes):
    responses.get(
        f"{API}/config/naming",
        json={
            "id": 1,
            "renameBooks": False,
            "replaceIllegalCharacters": True,
            "colonReplacementFormat": 0,
            "standardBookFormat": "{Book Title}",
            "authorFolderFormat": "{Author Name}",
        },
    )
    put = responses.put(f"{API}/config/naming/1", json={"id": 1})
    p = _provider(tmp_path, "bookshelf.naming")
    plan = plan_provider(p)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(p, plan)
    body = json.loads(put.calls[0].request.body)
    assert body["renameBooks"] is True
    assert body["colonReplacementFormat"] == 4  # int, like Sonarr
    assert body["authorFolderFormat"] == "{Author Name}"


@responses.activate
def test_download_client_on_v1(tmp_path, plan_provider):
    responses.get(f"{API}/downloadclient", json=[])
    responses.get(
        f"{API}/downloadclient/schema",
        json=[
            {
                "implementation": "Sabnzbd",
                "configContract": "SabnzbdSettings",
                "protocol": "usenet",
                "fields": [
                    {"name": "host", "value": "localhost"},
                    {"name": "musicCategory", "value": "Readarr"},
                ],
            }
        ],
    )
    plan = plan_provider(_provider(tmp_path, "bookshelf.download_client"))
    [res] = plan.resources
    assert res.op is Op.CREATE


# A trimmed GET /qualityprofile/schema (QualityProfileService.GetDefaultProfile):
# Readarr's qualities are ebook/audio formats.
QP_SCHEMA = {
    "name": "",
    "upgradeAllowed": False,
    "cutoff": 0,
    "items": [
        {"quality": {"id": 0, "name": "Unknown Text"}, "items": [], "allowed": False},
        {"quality": {"id": 1, "name": "PDF"}, "items": [], "allowed": False},
        {"quality": {"id": 2, "name": "MOBI"}, "items": [], "allowed": False},
        {"quality": {"id": 3, "name": "EPUB"}, "items": [], "allowed": False},
        {"quality": {"id": 4, "name": "AZW3"}, "items": [], "allowed": False},
        {"quality": {"id": 10, "name": "MP3"}, "items": [], "allowed": False},
    ],
    "minFormatScore": 0,
    "cutoffFormatScore": 0,
    "formatItems": [{"format": 1, "name": "Retail", "score": 0}],
}


@responses.activate
def test_quality_profile_with_readarr_qualities(tmp_path, plan_provider, apply_changes):
    responses.get(f"{API}/qualityprofile", json=[])
    responses.get(f"{API}/qualityprofile/schema", json=QP_SCHEMA)
    post = responses.post(f"{API}/qualityprofile", json={"id": 1})
    p = _provider(tmp_path, "bookshelf.quality_profile")
    plan = plan_provider(p)
    assert [(r.key, r.op) for r in plan.resources] == [("eBook", Op.CREATE)]
    apply_changes(p, plan)
    body = json.loads(post.calls[0].request.body)
    allowed = [i["quality"]["name"] for i in body["items"] if i["allowed"]]
    assert allowed == ["EPUB", "AZW3", "MOBI"]
    assert body["cutoff"] == 3  # EPUB
    assert "language" not in body


@responses.activate
def test_prowlarr_readarr_application(plan_provider):
    # Prowlarr's Readarr application is schema-driven like Sonarr/Radarr.
    prowlarr = "http://prowlarr.test"
    responses.get(f"{prowlarr}/api/v1/applications", json=[])
    responses.get(
        f"{prowlarr}/api/v1/applications/schema",
        json=[
            {
                "implementation": "Readarr",
                "configContract": "ReadarrSettings",
                "fields": [
                    {"name": "prowlarrUrl", "value": ""},
                    {"name": "baseUrl", "value": "http://localhost:8787"},
                    {"name": "apiKey", "value": "", "privacy": "apiKey"},
                ],
            }
        ],
    )
    p = ApplicationProvider(
        prowlarr,
        "k",
        {
            "Bookshelf": {
                "implementation": "Readarr",
                "settings": {
                    "prowlarrUrl": "http://prowlarr:9696",
                    "baseUrl": BOOKSHELF,
                    "apiKey": "secret",
                },
            }
        },
        "prowlarr.application",
    )
    plan = plan_provider(p)
    [res] = plan.resources
    assert (res.key, res.op) == ("Bookshelf", Op.CREATE)
    [desired] = p.build_desired()
    fields = {f["name"]: f["value"] for f in desired["fields"]}
    assert fields["baseUrl"] == BOOKSHELF
    assert desired["implementation"] == "Readarr"
