from configarr.diff.registry import providers_for
from configarr.models import ArrServiceConfig, ConfigarrConfig


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
    assert all(p.service == "radarr" for p in planned)


def test_service_filter_narrows_to_matching_service():
    config = ConfigarrConfig(radarr=[_radarr("hd")])

    assert all(p.service == "radarr" for p in providers_for(config, service="radarr"))
    assert list(providers_for(config, service="sonarr")) == []


def test_instance_filter_narrows_to_one_instance():
    config = ConfigarrConfig(radarr=[_radarr("hd"), _radarr("uhd")])

    planned = list(providers_for(config, instance="uhd"))

    assert {p.instance for p in planned} == {"uhd"}
