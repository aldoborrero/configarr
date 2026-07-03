from configarr.models import (
    ArrServiceConfig,
    BazarrConfig,
    ConfigarrConfig,
    ProwlarrConfig,
    SabnzbdConfig,
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
    assert _instances_for_kind(planned, "bazarr.provider") == ["subs"]
    assert _instances_for_kind(planned, "radarr.general") == []


def test_service_filter_narrows_to_matching_service():
    config = ConfigarrConfig(radarr=[_radarr("hd")])

    assert all(p.service == "radarr" for p in providers_for(config, service="radarr"))
    assert list(providers_for(config, service="sonarr")) == []


def test_instance_filter_narrows_to_one_instance():
    config = ConfigarrConfig(radarr=[_radarr("hd"), _radarr("uhd")])

    planned = list(providers_for(config, instance="uhd"))

    assert {p.instance for p in planned} == {"uhd"}
