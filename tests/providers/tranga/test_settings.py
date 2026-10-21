import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.tranga.settings import TrangaSettingsProvider

T = "http://tranga.test"
S = f"{T}/v2/Settings"

# Shape of a live GET /v2/Settings (Tranga v2).
CURRENT = {
    "userAgent": "Tranga/2.0 (Unix; x64)",
    "imageCompression": 40,
    "blackWhiteImages": False,
    "flareSolverrUrl": "",
    "chapterNamingScheme": "%M - ?V(Vol.%V )Ch.%C?T( - %T)",
    "workCycleTimeoutMs": 20000,
    "downloadLanguage": "en",
    "maxConcurrentDownloads": 7,
    "maxConcurrentWorkers": 10,
    "libraryRefreshSetting": "AfterMangaFinished",
    "refreshLibraryWhileDownloadingEveryMinutes": 10,
}


def _provider(config, api_key=""):
    return TrangaSettingsProvider(T, api_key, config, "tranga.settings")


@responses.activate
def test_one_call_per_changed_setting(plan_provider, apply_changes):
    responses.get(S, json=CURRENT)
    lang = responses.patch(f"{S}/DownloadLanguage/es")
    flare = responses.patch(f"{S}/FlareSolverr/Url")
    bw = responses.patch(f"{S}/BWImages/true")
    provider = _provider(
        {
            "download_language": "es",
            "flaresolverr_url": "http://flaresolverr:8191",
            "black_white_images": True,
            "image_compression": 40,  # unchanged: no call
        }
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    assert {d.path for d in plan.resources[0].field_diffs} == {
        "downloadLanguage",
        "flareSolverrUrl",
        "blackWhiteImages",
    }
    apply_changes(provider, plan)
    assert lang.call_count == flare.call_count == bw.call_count == 1
    assert json.loads(flare.calls[0].request.body) == "http://flaresolverr:8191"
    writes = [c for c in responses.calls if c.request.method != "GET"]
    assert len(writes) == 3
    assert "X-Api-Key" not in responses.calls[0].request.headers


@responses.activate
def test_unchanged_settings_plan_nothing(plan_provider):
    responses.get(S, json=CURRENT)
    provider = _provider({"download_language": "en", "image_compression": 40})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UNCHANGED]


@responses.activate
def test_library_refresh_sends_both_fields(plan_provider, apply_changes):
    responses.get(S, json=CURRENT)
    refresh = responses.patch(f"{S}/LibraryRefresh")
    provider = _provider({"library_refresh_setting": "while_downloading"})
    apply_changes(provider, plan_provider(provider))
    assert json.loads(refresh.calls[0].request.body) == {
        "setting": "WhileDownloading",
        "refreshLibraryWhileDownloadingEveryMinutes": 10,
    }


@responses.activate
def test_string_settings_send_json_string_bodies(plan_provider, apply_changes):
    responses.get(S, json=CURRENT)
    ua = responses.patch(f"{S}/UserAgent")
    scheme = responses.patch(f"{S}/ChapterNamingScheme")
    provider = _provider({"user_agent": "configarr", "chapter_naming_scheme": "%M %C"})
    apply_changes(provider, plan_provider(provider))
    assert json.loads(ua.calls[0].request.body) == "configarr"
    assert json.loads(scheme.calls[0].request.body) == "%M %C"


@responses.activate
def test_empty_flaresolverr_url_clears_it(plan_provider, apply_changes):
    responses.get(S, json={**CURRENT, "flareSolverrUrl": "http://old:8191"})
    clear = responses.delete(f"{S}/FlareSolverr/Url")
    provider = _provider({"flaresolverr_url": ""})
    apply_changes(provider, plan_provider(provider))
    assert clear.call_count == 1


@responses.activate
def test_api_key_is_sent_when_configured(plan_provider):
    responses.get(S, json=CURRENT)
    plan_provider(_provider({"download_language": "en"}, api_key="proxy"))
    assert responses.calls[0].request.headers["X-Api-Key"] == "proxy"


def test_read_only_setting_is_rejected():
    with pytest.raises(ValueError, match="max_concurrent_workers"):
        _provider({"max_concurrent_workers": 4})


def test_image_compression_out_of_range_is_rejected():
    with pytest.raises(ValueError, match=r"1\.\.100"):
        _provider({"image_compression": 0})


@responses.activate
def test_unknown_refresh_setting_is_rejected(plan_provider):
    responses.get(S, json=CURRENT)
    with pytest.raises(ValueError, match="library_refresh_setting"):
        plan_provider(_provider({"library_refresh_setting": "sometimes"}))


def test_no_config_reads_nothing(plan_provider):
    assert plan_provider(_provider(None)).resources == []
