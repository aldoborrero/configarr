from configarr.models import (
    ArrServiceConfig,
    BazarrConfig,
    CleanuparrConfig,
    ConfigarrConfig,
    KavitaConfig,
    KapowarrConfig,
    LingarrConfig,
    ProwlarrConfig,
    SabnzbdConfig,
    TrangaConfig,
)
from configarr.registry import providers_for


def _radarr(name: str) -> ArrServiceConfig:
    return ArrServiceConfig(
        name=name,
        base_url=f"http://{name}.test",
        api_key="k",
        custom_formats={"x265": {"specifications": []}},
    )


def _instances_for_kind(planned, kind):
    return [p.instance for p in planned if p.provider.kind == kind]


def test_yields_a_provider_per_radarr_instance():
    config = ConfigarrConfig(radarr=[_radarr("hd"), _radarr("uhd")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "radarr.custom_format") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.quality_profile") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.quality_definition") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.naming") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.root_folder") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.delay_profile") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.download_client") == ["hd", "uhd"]
    assert _instances_for_kind(planned, "radarr.notification") == ["hd", "uhd"]
    assert all(p.service == "radarr" for p in planned)


def _sonarr(name: str) -> ArrServiceConfig:
    return ArrServiceConfig(
        name=name,
        base_url=f"http://{name}.test",
        api_key="k",
    )


def test_release_profile_is_sonarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], sonarr=[_sonarr("tv")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "sonarr.release_profile") == ["tv"]
    assert _instances_for_kind(planned, "radarr.release_profile") == []


def test_custom_format_provider_covers_both_radarr_and_sonarr():
    # Sonarr supports custom formats via the same /api/v3/customformat API, so a
    # sonarr instance that declares custom_formats must get a provider too.
    sonarr_cf = ArrServiceConfig(
        name="tv",
        base_url="http://tv.test",
        api_key="k",
        custom_formats={"x265": {"specifications": []}},
    )
    config = ConfigarrConfig(radarr=[_radarr("hd")], sonarr=[sonarr_cf])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "radarr.custom_format") == ["hd"]
    assert _instances_for_kind(planned, "sonarr.custom_format") == ["tv"]


def _prowlarr(name: str) -> ProwlarrConfig:
    return ProwlarrConfig(
        name=name,
        base_url=f"http://{name}.test",
        api_key="k",
    )


def test_indexer_is_prowlarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], prowlarr=[_prowlarr("idx")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "prowlarr.indexer") == ["idx"]
    assert _instances_for_kind(planned, "radarr.indexer") == []


def test_application_is_prowlarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], prowlarr=[_prowlarr("app")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "prowlarr.application") == ["app"]
    assert _instances_for_kind(planned, "radarr.application") == []


def test_prowlarr_download_client_is_prowlarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], prowlarr=[_prowlarr("dl")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "prowlarr.download_client") == ["dl"]
    assert _instances_for_kind(planned, "radarr.download_client") == ["hd"]


def _sabnzbd(name: str) -> SabnzbdConfig:
    return SabnzbdConfig(
        name=name,
        base_url=f"http://{name}.test",
        api_key="k",
    )


def test_sabnzbd_server_is_sabnzbd_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], sabnzbd=[_sabnzbd("sab")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "sabnzbd.server") == ["sab"]
    assert _instances_for_kind(planned, "radarr.server") == []


def test_sabnzbd_category_is_sabnzbd_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], sabnzbd=[_sabnzbd("sab")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "sabnzbd.category") == ["sab"]
    assert _instances_for_kind(planned, "radarr.category") == []


def test_sabnzbd_misc_is_sabnzbd_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], sabnzbd=[_sabnzbd("sab")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "sabnzbd.misc") == ["sab"]
    assert _instances_for_kind(planned, "radarr.misc") == []


def _bazarr(name: str) -> BazarrConfig:
    return BazarrConfig(
        name=name,
        base_url=f"http://{name}.test",
        api_key="k",
    )


def test_bazarr_settings_are_bazarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], bazarr=[_bazarr("subs")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "bazarr.general") == ["subs"]
    assert _instances_for_kind(planned, "bazarr.sonarr") == ["subs"]
    assert _instances_for_kind(planned, "bazarr.radarr") == ["subs"]
    assert _instances_for_kind(planned, "bazarr.subsync") == ["subs"]
    assert _instances_for_kind(planned, "bazarr.translator") == ["subs"]
    assert _instances_for_kind(planned, "bazarr.provider") == ["subs"]
    assert _instances_for_kind(planned, "radarr.general") == []


def _lingarr(name: str) -> LingarrConfig:
    return LingarrConfig(name=name, base_url=f"http://{name}.test")


def test_lingarr_settings_are_lingarr_only():
    config = ConfigarrConfig(radarr=[_radarr("hd")], lingarr=[_lingarr("main")])

    planned = list(providers_for(config))

    assert _instances_for_kind(planned, "lingarr.translation") == ["main"]
    assert _instances_for_kind(planned, "lingarr.integration") == ["main"]
    assert _instances_for_kind(planned, "lingarr.automation") == ["main"]
    assert _instances_for_kind(planned, "lingarr.validation") == ["main"]
    assert _instances_for_kind(planned, "lingarr.onboarding") == ["main"]
    assert _instances_for_kind(planned, "radarr.translation") == []


def test_service_filter_narrows_to_matching_service():
    config = ConfigarrConfig(radarr=[_radarr("hd")])

    assert all(p.service == "radarr" for p in providers_for(config, service="radarr"))
    assert list(providers_for(config, service="sonarr")) == []


def test_instance_filter_narrows_to_one_instance():
    config = ConfigarrConfig(radarr=[_radarr("hd"), _radarr("uhd")])

    planned = list(providers_for(config, instance="uhd"))

    assert {p.instance for p in planned} == {"uhd"}


def test_cleanuparr_providers_are_cleanuparr_only_and_ordered():
    config = ConfigarrConfig(
        radarr=[_radarr("hd")],
        cleanuparr=[
            CleanuparrConfig(name="main", base_url="http://c.test", api_key="k")
        ],
    )

    planned = list(providers_for(config))
    kinds = [p.provider.kind for p in planned if p.service == "cleanuparr"]

    assert kinds == [
        "cleanuparr.general",
        "cleanuparr.arr_settings",
        "cleanuparr.arr_instance",
        "cleanuparr.download_client",
        "cleanuparr.client_settings",
        "cleanuparr.seeding_rule",
        "cleanuparr.queue_cleaner",
        "cleanuparr.download_cleaner",
        "cleanuparr.malware_blocker",
    ]
    assert _instances_for_kind(planned, "cleanuparr.queue_cleaner") == ["main"]


def test_kavita_providers_are_kavita_only_and_libraries_first():
    config = ConfigarrConfig(
        radarr=[_radarr("hd")],
        kavita=[KavitaConfig(name="main", base_url="http://kv.test", api_key="k")],
    )

    planned = list(providers_for(config))
    kinds = [p.provider.kind for p in planned if p.service == "kavita"]

    assert kinds == ["kavita.library", "kavita.settings"]
    assert _instances_for_kind(planned, "kavita.settings") == ["main"]


def test_kapowarr_providers_are_kapowarr_only_and_ordered():
    config = ConfigarrConfig(
        radarr=[_radarr("hd")],
        kapowarr=[KapowarrConfig(name="main", base_url="http://k.test", api_key="k")],
    )

    planned = list(providers_for(config))
    kinds = [p.provider.kind for p in planned if p.service == "kapowarr"]

    assert kinds == [
        "kapowarr.settings",
        "kapowarr.root_folder",
        "kapowarr.download_client",
        "kapowarr.credential",
    ]
    assert _instances_for_kind(planned, "kapowarr.root_folder") == ["main"]


def test_tranga_providers_are_tranga_only_and_ordered():
    config = ConfigarrConfig(
        radarr=[_radarr("hd")],
        tranga=[TrangaConfig(name="main", base_url="http://t.test")],
    )

    planned = list(providers_for(config))
    kinds = [p.provider.kind for p in planned if p.service == "tranga"]

    assert kinds == [
        "tranga.settings",
        "tranga.file_library",
        "tranga.library_connector",
        "tranga.notification_connector",
    ]
    assert _instances_for_kind(planned, "tranga.settings") == ["main"]
