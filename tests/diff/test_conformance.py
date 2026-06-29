"""Every registered provider must conform to the ResourceProvider seam the
runner/registry depend on. This is the runtime complement to nix/checks/mypy.nix:
the static check catches signature drift, this catches a provider that drops a
required attribute/method outright."""

from configarr.diff.providers.base import ResourceProvider
from configarr.diff.registry import providers_for
from configarr.models import ArrServiceConfig, ConfigarrConfig


def test_every_registered_provider_isinstance_conforms():
    config = ConfigarrConfig(
        radarr=[
            ArrServiceConfig(
                name="r",
                base_url="http://r.test",
                api_key="k",
                custom_formats={},
            )
        ],
    )

    planned = list(providers_for(config))

    assert planned, "registry yielded no providers for a radarr config"
    for p in planned:
        assert isinstance(p.provider, ResourceProvider), p.provider.kind
