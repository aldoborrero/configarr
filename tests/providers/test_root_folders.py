import responses

from configarr.model import Op
from configarr.providers.arr.root_folders import RootFolderProvider

RADARR = "http://radarr.test"
SONARR = "http://sonarr.test"

CONFIG = [{"path": "/movies"}, {"path": "/movies2"}]


def _radarr(config):
    return RootFolderProvider(
        base_url=RADARR, api_key="k", config=config, kind="radarr.root_folder"
    )


def _sonarr(config):
    return RootFolderProvider(
        base_url=SONARR, api_key="k", config=config, kind="sonarr.root_folder"
    )


@responses.activate
def test_absent_folders_plan_as_create(plan_provider):
    responses.get(f"{RADARR}/api/v3/rootfolder", json=[])
    plan = plan_provider(_radarr(CONFIG))
    assert [r.key for r in plan.resources] == ["/movies", "/movies2"]
    assert all(r.op is Op.CREATE for r in plan.resources)


@responses.activate
def test_existing_folder_is_unchanged(plan_provider):
    responses.get(
        f"{RADARR}/api/v3/rootfolder",
        json=[
            {"id": 1, "path": "/movies", "accessible": True, "freeSpace": 1234},
            {"id": 2, "path": "/movies2", "accessible": True, "freeSpace": 5678},
        ],
    )
    plan = plan_provider(_radarr(CONFIG))
    assert not plan.has_changes, plan.resources


@responses.activate
def test_no_config_plans_nothing(plan_provider):
    responses.get(f"{RADARR}/api/v3/rootfolder", json=[])
    plan = plan_provider(_radarr(None))
    assert not plan.resources


@responses.activate
def test_build_desired_emits_only_path(plan_provider):
    desired = _sonarr([{"path": "/tv"}]).build_desired()
    assert desired == [{"path": "/tv"}]


@responses.activate
def test_apply_then_replan_is_noop(plan_provider, apply_changes):
    responses.get(f"{RADARR}/api/v3/rootfolder", json=[])
    responses.post(
        f"{RADARR}/api/v3/rootfolder",
        json={"id": 1, "path": "/movies", "accessible": True},
    )
    responses.post(
        f"{RADARR}/api/v3/rootfolder",
        json={"id": 2, "path": "/movies2", "accessible": True},
    )
    p = _radarr(CONFIG)
    apply_changes(p, plan_provider(p))

    responses.reset()
    responses.get(
        f"{RADARR}/api/v3/rootfolder",
        json=[
            {"id": 1, "path": "/movies", "accessible": True},
            {"id": 2, "path": "/movies2", "accessible": True},
        ],
    )
    plan2 = plan_provider(p)
    assert not plan2.has_changes, plan2.resources
