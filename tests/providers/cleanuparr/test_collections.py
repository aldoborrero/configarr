import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.cleanuparr.collections import (
    CleanuparrArrInstanceProvider,
    CleanuparrDownloadClientProvider,
)
from configarr.providers.cleanuparr.common import SECRET_PLACEHOLDER

CU = "http://cleanuparr.test"
DC = f"{CU}/api/configuration/download_client"

SAB = {
    "id": "guid-sab",
    "enabled": True,
    "name": "SABnzbd",
    "typeName": "Sabnzbd",
    "type": "Usenet",
    "host": "http://sab:8080",
    "username": None,
    "password": None,
    "apiKey": SECRET_PLACEHOLDER,
    "urlBase": None,
    "externalUrl": None,
    "downloadDirectorySource": None,
    "downloadDirectoryTarget": None,
}


def _clients(config):
    return CleanuparrDownloadClientProvider(
        CU, "key", config, "cleanuparr.download_client"
    )


def _instances(arr):
    return CleanuparrArrInstanceProvider(CU, "key", arr, "cleanuparr.arr_instance")


# -- download clients ---------------------------------------------------------


@responses.activate
def test_new_client_is_created_with_canonical_type(plan_provider, apply_changes):
    responses.get(DC, json={"clients": []})
    responses.post(DC, json={}, status=201)
    provider = _clients(
        {"SABnzbd": {"type": "sabnzbd", "host": "http://sab:8080", "api_key": "s"}}
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.CREATE]
    apply_changes(provider, plan)
    body = json.loads(responses.calls[-1].request.body)
    assert body == {
        "enabled": True,
        "name": "SABnzbd",
        "typeName": "Sabnzbd",
        "host": "http://sab:8080",
        "apiKey": "s",
    }


@responses.activate
def test_unchanged_client_is_noop_even_with_secret_set(plan_provider):
    responses.get(DC, json={"clients": [SAB]})
    plan = plan_provider(
        _clients({"SABnzbd": {"host": "http://sab:8080", "api_key": "real"}})
    )
    # The secret is masked server-side, so it can't (and doesn't) diff.
    assert not plan.has_changes


@responses.activate
def test_update_sends_placeholder_for_unset_secret(plan_provider, apply_changes):
    responses.get(DC, json={"clients": [SAB]})
    responses.put(f"{DC}/guid-sab", json={})
    provider = _clients({"SABnzbd": {"enabled": False}})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(provider, plan)
    body = json.loads(responses.calls[-1].request.body)
    assert body["enabled"] is False
    assert body["apiKey"] == SECRET_PLACEHOLDER  # keeps the stored key
    assert body["host"] == "http://sab:8080"  # carried over from current
    assert body["id"] == "guid-sab"


@responses.activate
def test_client_type_cannot_change(plan_provider):
    responses.get(DC, json={"clients": [SAB]})
    with pytest.raises(ValueError, match="type cannot change"):
        plan_provider(_clients({"SABnzbd": {"type": "qbittorrent"}}))


@responses.activate
def test_new_client_requires_type(plan_provider):
    responses.get(DC, json={"clients": []})
    with pytest.raises(ValueError, match="missing required 'type'"):
        plan_provider(_clients({"New": {"host": "http://x"}}))


@responses.activate
def test_unknown_client_type_is_rejected(plan_provider):
    responses.get(DC, json={"clients": []})
    with pytest.raises(ValueError, match="unknown download client type"):
        plan_provider(_clients({"X": {"type": "nzbget", "host": "http://x"}}))


@responses.activate
def test_unmanaged_client_is_pruned_only_with_prune(plan_provider, apply_changes):
    other = {**SAB, "id": "guid-old", "name": "Old"}
    responses.get(DC, json={"clients": [SAB, other]})
    responses.delete(f"{DC}/guid-old", status=204)
    provider = _clients({"SABnzbd": {}})
    assert not plan_provider(provider).has_changes
    plan = plan_provider(provider, prune=True)
    assert [(r.op, r.key) for r in plan.resources if r.changed] == [(Op.DELETE, "Old")]
    apply_changes(provider, plan)
    assert responses.calls[-1].request.method == "DELETE"


# -- arr instances ------------------------------------------------------------


def _mock_arr(arr_type, instances):
    responses.get(
        f"{CU}/api/configuration/{arr_type}",
        json={"id": "cfg", "type": arr_type.title(), "instances": instances},
    )


SONARR = {
    "id": "guid-son",
    "enabled": True,
    "version": 4,
    "name": "Sonarr",
    "url": "http://sonarr:8989/",
    "apiKey": SECRET_PLACEHOLDER,
    "externalUrl": None,
}


@responses.activate
def test_instance_url_trailing_slash_is_not_a_diff(plan_provider):
    _mock_arr("sonarr", [SONARR])
    plan = plan_provider(
        _instances(
            {
                "sonarr": {
                    "instances": {"Sonarr": {"url": "http://sonarr:8989", "version": 4}}
                }
            }
        )
    )
    assert not plan.has_changes


@responses.activate
def test_new_instance_posts_to_its_arr_type(plan_provider, apply_changes):
    _mock_arr("radarr", [])
    responses.post(f"{CU}/api/configuration/radarr/instances", json={}, status=201)
    provider = _instances(
        {
            "radarr": {
                "instances": {
                    "Radarr": {
                        "url": "http://radarr:7878",
                        "api_key": "k",
                        "version": 6,
                    }
                }
            }
        }
    )
    plan = plan_provider(provider)
    assert [(r.op, r.key) for r in plan.resources] == [
        (Op.CREATE, ("radarr", "Radarr"))
    ]
    apply_changes(provider, plan)
    body = json.loads(responses.calls[-1].request.body)
    assert body == {
        "enabled": True,
        "name": "Radarr",
        "url": "http://radarr:7878",
        "apiKey": "k",
        "version": 6,
    }


@responses.activate
def test_new_instance_requires_version(plan_provider):
    _mock_arr("sonarr", [])
    with pytest.raises(ValueError, match="missing required 'version'"):
        plan_provider(
            _instances(
                {"sonarr": {"instances": {"S": {"url": "http://s", "api_key": "k"}}}}
            )
        )


@responses.activate
def test_instance_update_and_delete_hit_the_instance_id(plan_provider, apply_changes):
    old = {**SONARR, "id": "guid-old", "name": "Old"}
    _mock_arr("sonarr", [SONARR, old])
    responses.put(f"{CU}/api/configuration/sonarr/instances/guid-son", json={})
    responses.delete(f"{CU}/api/configuration/sonarr/instances/guid-old", status=204)
    provider = _instances({"sonarr": {"instances": {"Sonarr": {"enabled": False}}}})
    plan = plan_provider(provider, prune=True)
    ops = {r.key: r.op for r in plan.resources if r.changed}
    assert ops == {("sonarr", "Sonarr"): Op.UPDATE, ("sonarr", "Old"): Op.DELETE}
    apply_changes(provider, plan)
    methods = [c.request.method for c in responses.calls if c.request.method != "GET"]
    assert sorted(methods) == ["DELETE", "PUT"]
    put = next(c for c in responses.calls if c.request.method == "PUT")
    assert json.loads(put.request.body)["apiKey"] == SECRET_PLACEHOLDER
