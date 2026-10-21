import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.kapowarr.collections import (
    KapowarrCredentialProvider,
    KapowarrDownloadClientProvider,
    KapowarrRootFolderProvider,
)
from configarr.providers.kapowarr.common import MASK

KP = "http://kapowarr.test"
API = f"{KP}/api"


def _ok(result):
    return {"error": None, "result": result}


def _body(call):
    return json.loads(call.request.body)


# -- root folders -------------------------------------------------------------


def _roots(config):
    return KapowarrRootFolderProvider(KP, "k", config, "kapowarr.root_folder")


@responses.activate
def test_existing_root_folder_matches_despite_trailing_slash(plan_provider):
    responses.get(f"{API}/rootfolder", json=_ok([{"id": 1, "folder": "/comics/"}]))
    plan = plan_provider(_roots([{"path": "/comics"}]))
    assert [r.op for r in plan.resources] == [Op.UNCHANGED]


@responses.activate
def test_root_folder_create_and_prune(plan_provider, apply_changes):
    responses.get(f"{API}/rootfolder", json=_ok([{"id": 7, "folder": "/old/"}]))
    responses.post(f"{API}/rootfolder", json=_ok({"id": 8}), status=201)
    responses.delete(f"{API}/rootfolder/7", json=_ok({}))
    provider = _roots([{"path": "/comics/"}])
    plan = plan_provider(provider, prune=True)
    assert {(r.key, r.op) for r in plan.resources} == {
        ("/comics", Op.CREATE),
        ("/old", Op.DELETE),
    }
    apply_changes(provider, plan)
    post = next(c for c in responses.calls if c.request.method == "POST")
    assert _body(post) == {"folder": "/comics"}
    assert any(c.request.method == "DELETE" for c in responses.calls)


# -- download clients ---------------------------------------------------------

TRANSMISSION = {
    "id": 3,
    "enabled": True,
    "download_type": 2,
    "client_type": "Transmission",
    "required_tokens": ["title", "enabled", "base_url", "username", "password"],
    "title": "Transmission",
    "base_url": "http://transmission:9091",
    "username": "user",
    "password": "pass",
    "api_token": None,
}


def _clients(config):
    return KapowarrDownloadClientProvider(KP, "k", config, "kapowarr.download_client")


@responses.activate
def test_new_client_is_created_with_canonical_type(plan_provider, apply_changes):
    responses.get(f"{API}/externalclients", json=_ok([]))
    responses.post(f"{API}/externalclients", json=_ok({"id": 4}), status=201)
    provider = _clients(
        {
            "Transmission": {
                "client_type": "transmission",
                "base_url": "http://transmission:9091",
                "username": "user",
                "password": "pass",
            }
        }
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.CREATE]
    assert "'pass'" not in str(plan.resources[0].field_diffs)
    apply_changes(provider, plan)
    assert _body(responses.calls[-1]) == {
        "download_type": 2,
        "client_type": "Transmission",
        "title": "Transmission",
        "enabled": True,
        "base_url": "http://transmission:9091",
        "username": "user",
        "password": "pass",
        "api_token": None,
    }


@responses.activate
def test_unchanged_client_is_noop(plan_provider):
    responses.get(f"{API}/externalclients", json=_ok([TRANSMISSION]))
    plan = plan_provider(
        _clients(
            {
                "Transmission": {
                    "client_type": "Transmission",
                    "base_url": "transmission:9091/",
                    "username": "user",
                    "password": "pass",
                }
            }
        )
    )
    assert not plan.has_changes


@responses.activate
def test_changed_password_updates_with_full_body(plan_provider, apply_changes):
    responses.get(f"{API}/externalclients", json=_ok([TRANSMISSION]))
    responses.put(f"{API}/externalclients/3", json=_ok(TRANSMISSION))
    provider = _clients({"Transmission": {"password": "new"}})
    plan = plan_provider(provider)
    [res] = plan.resources
    assert res.op is Op.UPDATE
    assert [d.path for d in res.field_diffs] == ["password"]
    apply_changes(provider, plan)
    assert _body(responses.calls[-1]) == {
        "title": "Transmission",
        "enabled": True,
        "base_url": "http://transmission:9091",
        "username": "user",
        "password": "new",
        "api_token": None,
    }


@responses.activate
def test_client_type_cannot_change(plan_provider):
    responses.get(f"{API}/externalclients", json=_ok([TRANSMISSION]))
    with pytest.raises(ValueError, match="cannot change"):
        plan_provider(_clients({"Transmission": {"client_type": "qbittorrent"}}))


@responses.activate
def test_new_client_needs_type_and_url(plan_provider):
    responses.get(f"{API}/externalclients", json=_ok([]))
    with pytest.raises(ValueError, match="client_type"):
        plan_provider(_clients({"T": {"base_url": "http://t"}}))


@responses.activate
def test_unknown_client_type_is_rejected(plan_provider):
    responses.get(f"{API}/externalclients", json=_ok([]))
    with pytest.raises(ValueError, match="unknown client_type"):
        plan_provider(_clients({"T": {"client_type": "deluge", "base_url": "x"}}))


@responses.activate
def test_unmanaged_client_is_pruned(plan_provider, apply_changes):
    responses.get(f"{API}/externalclients", json=_ok([TRANSMISSION]))
    responses.delete(f"{API}/externalclients/3", json=_ok({}))
    provider = _clients({})
    provider.config = {"Other": {"client_type": "qBittorrent", "base_url": "http://q"}}
    responses.post(f"{API}/externalclients", json=_ok({"id": 9}), status=201)
    plan = plan_provider(provider, prune=True)
    assert {(r.key, r.op) for r in plan.resources} == {
        ("Other", Op.CREATE),
        ("Transmission", Op.DELETE),
    }
    apply_changes(provider, plan)
    assert [c.request.method for c in responses.calls].count("DELETE") == 1


# -- credentials --------------------------------------------------------------

MEGA = {
    "id": 5,
    "source": "mega",
    "username": None,
    "email": "me@example.com",
    "password": MASK,
    "api_key": None,
}


def _creds(config):
    return KapowarrCredentialProvider(KP, "k", config, "kapowarr.credential")


@responses.activate
def test_unchanged_credential_is_noop(plan_provider):
    responses.get(f"{API}/credentials", json=_ok([MEGA]))
    plan = plan_provider(
        _creds({"mega": {"email": "me@example.com", "password": "secret"}})
    )
    assert not plan.has_changes


@responses.activate
def test_changed_credential_is_recreated_then_old_deleted(plan_provider, apply_changes):
    responses.get(f"{API}/credentials", json=_ok([MEGA]))
    responses.post(f"{API}/credentials", json=_ok({**MEGA, "id": 6}), status=201)
    responses.delete(f"{API}/credentials/5", json=_ok({}))
    provider = _creds({"mega": {"email": "new@example.com", "password": "secret"}})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(provider, plan)
    methods = [c.request.method for c in responses.calls]
    assert methods[-2:] == ["POST", "DELETE"]
    post = responses.calls[len(methods) - 2]
    assert _body(post) == {
        "source": "mega",
        "email": "new@example.com",
        "password": "secret",
    }


@responses.activate
def test_pixeldrain_api_key_is_fingerprinted(plan_provider):
    responses.get(
        f"{API}/credentials",
        json=_ok([{**MEGA, "source": "pixeldrain", "email": None, "api_key": "a"}]),
    )
    plan = plan_provider(_creds({"pixeldrain": {"api_key": "b"}}))
    [res] = plan.resources
    assert res.op is Op.UPDATE
    assert "'b'" not in str(res.field_diffs)


def test_unknown_credential_source_is_rejected():
    with pytest.raises(ValueError, match="unknown source"):
        _creds({"rapidgator": {"api_key": "x"}})


@responses.activate
def test_credential_missing_field_is_rejected(plan_provider):
    responses.get(f"{API}/credentials", json=_ok([]))
    with pytest.raises(ValueError, match="password"):
        plan_provider(_creds({"mega": {"email": "me@example.com"}}))
