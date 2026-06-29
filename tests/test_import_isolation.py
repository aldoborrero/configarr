import sys


def test_diff_layer_does_not_import_generated_clients():
    # Importing the diff layer must not pull in the nix-only generated API
    # clients or configarr.sync (they are absent from the test env on purpose).
    import configarr.diff.runner  # noqa: F401

    forbidden = {"radarr", "sonarr", "prowlarr", "bazarr", "sabnzbd", "configarr.sync"}
    leaked = forbidden & set(sys.modules)
    assert not leaked, f"diff layer pulled forbidden modules: {sorted(leaked)}"
