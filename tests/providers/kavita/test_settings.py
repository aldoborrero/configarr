import copy
import json
import logging

import pytest
import responses

from configarr.plan import Op
from configarr.providers.kavita.settings import KavitaSettingsProvider

KV = "http://kavita.test"

# Trimmed from a live Kavita 0.9.1.4 GET /api/settings (secret masked as Kavita
# masks it: one '*' per character).
SETTINGS = {
    "cacheDirectory": "/app/kavita/config/cache",
    "taskScan": "daily",
    "taskBackup": "daily",
    "loggingLevel": "Information",
    "enableOpds": True,
    "installVersion": "0.9.1.4",
    "installId": "abc",
    "encodeMediaAs": 0,
    "totalBackups": 30,
    "enableFolderWatching": False,
    "hostName": "https://kavita.example",
    "coverImageSize": 1,
    "smtpConfig": {"host": "", "port": 0, "password": "hunter2", "enableSsl": True},
    "oidcConfig": {
        "authority": "https://auth.example",
        "clientId": "123",
        "secret": "******",
        "provisionAccounts": True,
        "customScopes": [],
        "defaultRoles": ["Login"],
        "defaultLibraries": [],
        "defaultAgeRestriction": 0,
        "enabled": True,
        "providerName": "OpenID Connect",
    },
    "statsApiHits": 30,
}


@pytest.fixture
def settings(kavita_auth):
    responses.get(f"{KV}/api/settings", json=copy.deepcopy(SETTINGS))


def _provider(config):
    return KavitaSettingsProvider(KV, "key", config, "kavita.settings")


@responses.activate
def test_change_plans_dotted_update(settings, plan_provider):
    plan = plan_provider(
        _provider(
            {
                "enable_folder_watching": True,
                "encode_media_as": "webp",
                "oidc": {"provider_name": "Zitadel"},
            }
        )
    )
    [res] = plan.resources
    assert res.op is Op.UPDATE
    diffs = {d.path: (d.before, d.after) for d in res.field_diffs}
    assert diffs == {
        "enableFolderWatching": (False, True),
        "encodeMediaAs": ("png", "webp"),
        "oidcConfig.providerName": ("OpenID Connect", "Zitadel"),
    }


@responses.activate
def test_matching_config_is_unchanged(settings, plan_provider, caplog):
    caplog.set_level(logging.WARNING)
    plan = plan_provider(
        _provider(
            {
                "host_name": "https://kavita.example/",
                "logging_level": "information",
                "oidc": {
                    "authority": "https://auth.example",
                    "client_id": "123",
                    # Same length as the stored one: indistinguishable, not a diff.
                    "secret": "s3cr3t",
                    "enabled": True,
                    "default_roles": ["Login"],
                },
                "smtp": {"password": "hunter2"},
            }
        )
    )
    assert not plan.has_changes
    assert "restart" not in caplog.text


@responses.activate
def test_post_carries_the_whole_dto(settings, plan_provider, apply_changes):
    responses.post(f"{KV}/api/settings", json={})
    provider = _provider({"enable_opds": False})
    apply_changes(provider, plan_provider(provider))
    body = json.loads(responses.calls[-1].request.body)
    assert body["enableOpds"] is False
    # Full-DTO POST: untouched settings go back unchanged, the OIDC secret as its
    # mask (Kavita keeps the stored secret), the SMTP password as stored.
    assert body["taskScan"] == "daily"
    assert body["oidcConfig"]["secret"] == "******"
    assert body["oidcConfig"]["defaultRoles"] == ["Login"]
    assert body["smtpConfig"]["password"] == "hunter2"


@responses.activate
def test_secrets_never_appear_in_the_plan(settings, plan_provider):
    plan = plan_provider(
        _provider(
            {"oidc": {"secret": "a-much-longer-secret"}, "smtp": {"password": "x"}}
        )
    )
    [res] = plan.resources
    diffs = {d.path: (d.before, d.after) for d in res.field_diffs}
    assert set(diffs) == {"oidcConfig.secret", "smtpConfig.password"}
    rendered = repr(diffs)
    assert "a-much-longer-secret" not in rendered
    assert "hunter2" not in rendered


@responses.activate
def test_oidc_identity_change_warns_about_restart(settings, plan_provider, caplog):
    caplog.set_level(logging.WARNING)
    plan_provider(_provider({"oidc": {"authority": "https://other.example"}}))
    assert "restart Kavita" in caplog.text
    assert "unlinks every user's existing OIDC login" in caplog.text


@responses.activate
def test_secret_change_warns_about_restart(settings, plan_provider, caplog):
    caplog.set_level(logging.WARNING)
    plan_provider(_provider({"oidc": {"secret": "longer-secret"}}))
    assert "restart Kavita" in caplog.text
    assert "unlinks" not in caplog.text


@responses.activate
def test_read_only_and_contradictory_enabled_are_ignored(
    settings, plan_provider, caplog
):
    caplog.set_level(logging.WARNING)
    plan = plan_provider(
        _provider({"install_version": "1.0", "oidc": {"enabled": False}})
    )
    assert not plan.has_changes
    assert "read-only" in caplog.text
    assert "derived from oidc.authority" in caplog.text


@responses.activate
def test_default_libraries_resolve_names_to_ids(settings, plan_provider):
    responses.get(
        f"{KV}/api/library/libraries", json=[{"id": 7, "name": "Libros", "type": 2}]
    )
    plan = plan_provider(
        _provider(
            {
                "oidc": {
                    "default_libraries": ["Libros"],
                    "default_age_restriction": "teen",
                }
            }
        )
    )
    [res] = plan.resources
    diffs = {d.path: d.after for d in res.field_diffs}
    assert diffs == {
        "oidcConfig.defaultLibraries": [7],
        "oidcConfig.defaultAgeRestriction": "teen",
    }


@responses.activate
def test_without_config_does_nothing(plan_provider):
    plan = plan_provider(_provider(None))
    assert plan.resources == []
    assert len(responses.calls) == 0
