"""Every registered provider must conform to the ResourceProvider seam the
runner/registry depend on. This is the runtime complement to nix/checks/mypy.nix:
the static check catches signature drift, this catches a provider that drops a
required attribute/method outright.

The fixture carries one instance of every service so all registered providers are
instantiated and checked — a radarr-only config would silently skip the 18
sonarr/prowlarr/sabnzbd/bazarr providers."""

from configarr.models import (
    ArrServiceConfig,
    BazarrConfig,
    ConfigarrConfig,
    ProwlarrConfig,
    SabnzbdConfig,
)
from configarr.providers.base import ResourceProvider
from configarr.registry import REGISTRY, providers_for


def _full_config() -> ConfigarrConfig:
    """A config with exactly one instance of every service, so providers_for
    instantiates every registered provider."""
    return ConfigarrConfig(
        radarr=[
            ArrServiceConfig(
                name="r",
                base_url="http://r.test",
                api_key="k",
            )
        ],
        sonarr=[
            ArrServiceConfig(
                name="s",
                base_url="http://s.test",
                api_key="k",
            )
        ],
        prowlarr=[
            ProwlarrConfig(
                name="p",
                base_url="http://p.test",
                api_key="k",
            )
        ],
        sabnzbd=[
            SabnzbdConfig(
                name="sab",
                base_url="http://sab.test",
                api_key="k",
            )
        ],
        bazarr=[
            BazarrConfig(
                name="b",
                base_url="http://b.test",
                api_key="k",
            )
        ],
    )


def test_every_registered_provider_isinstance_conforms():
    planned = list(providers_for(_full_config()))

    assert planned, "registry yielded no providers"
    for p in planned:
        assert isinstance(p.provider, ResourceProvider), p.provider.kind


def test_full_config_exercises_every_registered_kind():
    """Guard against a service silently dropping out of the fixture: every kind
    in the registry must be instantiated by the full config."""
    planned_kinds = {p.provider.kind for p in providers_for(_full_config())}
    registered_kinds = {reg.kind for reg in REGISTRY}

    assert planned_kinds == registered_kinds
