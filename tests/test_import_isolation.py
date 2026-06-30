import sys


def test_configarr_does_not_import_generated_clients():
    # configarr talks to each service's HTTP API directly via requests; the
    # nix-only generated API clients must never be pulled in (importing the CLI
    # entrypoint exercises the whole import graph).
    import configarr.__main__  # noqa: F401

    forbidden = {"radarr", "sonarr", "prowlarr", "bazarr", "sabnzbd"}
    leaked = forbidden & set(sys.modules)
    assert not leaked, f"configarr pulled forbidden modules: {sorted(leaked)}"
