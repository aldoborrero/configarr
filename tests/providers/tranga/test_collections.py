import json

import pytest
import requests
import responses

from configarr.plan import Op
from configarr.providers.tranga.collections import (
    TrangaFileLibraryProvider,
    TrangaLibraryConnectorProvider,
    TrangaNotificationConnectorProvider,
)

T = "http://tranga.test"
FL = f"{T}/v2/FileLibrary"
LC = f"{T}/v2/LibraryConnector"
NC = f"{T}/v2/NotificationConnector"

DEFAULT_LIB = {
    "basePath": "/Manga",
    "libraryName": "Default FileLibrary",
    "key": "FileLibrary-e0cd03e19cbea417b890e7f65be7c7bd",
}
KAVITA = {
    "baseUrl": "http://kavita:5000",
    "type": "Kavita",
    "key": "LibraryConnector-0123456789abcdef",
}


# -- file libraries -------------------------------------------------------------


def _libraries(config):
    return TrangaFileLibraryProvider(T, "", config, "tranga.file_library")


@responses.activate
def test_new_library_is_created_with_put(plan_provider, apply_changes):
    responses.get(FL, json=[DEFAULT_LIB])
    create = responses.put(FL, body="FileLibrary-new", status=201)
    provider = _libraries({"Comics": {"base_path": "/Comics"}})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.CREATE]
    apply_changes(provider, plan)
    assert json.loads(create.calls[0].request.body) == {
        "basePath": "/Comics",
        "libraryName": "Comics",
    }


@responses.activate
def test_library_path_change_patches_in_place(plan_provider, apply_changes):
    responses.get(FL, json=[DEFAULT_LIB])
    patch = responses.patch(f"{FL}/{DEFAULT_LIB['key']}")
    provider = _libraries({"Default FileLibrary": {"base_path": "/manga"}})
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(provider, plan)
    assert json.loads(patch.calls[0].request.body) == {
        "path": "/manga",
        "name": "Default FileLibrary",
    }


@responses.activate
def test_matching_library_is_unchanged_and_unmanaged_is_pruned(plan_provider):
    other = {**DEFAULT_LIB, "libraryName": "Old", "key": "FileLibrary-old0000000"}
    responses.get(FL, json=[DEFAULT_LIB, other])
    provider = _libraries({"Default FileLibrary": {"base_path": "/Manga"}})
    plan = plan_provider(provider, prune=True)
    assert {r.key: r.op for r in plan.resources} == {
        "Default FileLibrary": Op.UNCHANGED,
        "Old": Op.DELETE,
    }


@responses.activate
def test_prune_deletes_by_key(plan_provider, apply_changes):
    responses.get(FL, json=[DEFAULT_LIB])
    delete = responses.delete(f"{FL}/{DEFAULT_LIB['key']}")
    provider = _libraries({"Comics": {"base_path": "/Comics"}})
    responses.put(FL, body="x", status=201)
    apply_changes(provider, plan_provider(provider, prune=True))
    assert delete.call_count == 1


@responses.activate
def test_new_library_without_base_path_is_rejected(plan_provider):
    responses.get(FL, json=[])
    with pytest.raises(ValueError, match="base_path"):
        plan_provider(_libraries({"Comics": {}}))


# -- library connectors ---------------------------------------------------------


def _connectors(config):
    return TrangaLibraryConnectorProvider(T, "", config, "tranga.library_connector")


@responses.activate
def test_kavita_connector_is_created(plan_provider, apply_changes):
    responses.get(LC, json=[])
    create = responses.put(f"{LC}/Kavita", body="LibraryConnector-x", status=201)
    provider = _connectors(
        [{"type": "kavita", "base_url": "http://kavita:5000/", "api_key": "secret"}]
    )
    plan = plan_provider(provider)
    assert [(r.key, r.op) for r in plan.resources] == [
        (("Kavita", "http://kavita:5000"), Op.CREATE)
    ]
    apply_changes(provider, plan)
    assert json.loads(create.calls[0].request.body) == {
        "url": "http://kavita:5000",
        "apiKey": "secret",
    }
    assert "secret" not in str(plan.resources[0].field_diffs)


@responses.activate
def test_existing_connector_is_unchanged_without_api_key(plan_provider):
    responses.get(LC, json=[KAVITA])
    provider = _connectors([{"type": "Kavita", "base_url": "http://kavita:5000"}])
    assert [r.op for r in plan_provider(provider).resources] == [Op.UNCHANGED]


@responses.activate
def test_unmanaged_connector_is_pruned(plan_provider, apply_changes):
    komga = {"baseUrl": "http://komga:25600", "type": "Komga", "key": "LC-komga-0001"}
    responses.get(LC, json=[KAVITA, komga])
    delete = responses.delete(f"{LC}/{komga['key']}")
    provider = _connectors([{"type": "kavita", "base_url": "http://kavita:5000"}])
    apply_changes(provider, plan_provider(provider, prune=True))
    assert delete.call_count == 1


@responses.activate
def test_new_connector_needs_api_key(plan_provider):
    responses.get(LC, json=[])
    with pytest.raises(ValueError, match="api_key"):
        plan_provider(_connectors([{"type": "komga", "base_url": "http://k"}]))


@responses.activate
def test_unknown_connector_type_is_rejected(plan_provider):
    responses.get(LC, json=[])
    with pytest.raises(ValueError, match="unknown library connector type"):
        plan_provider(_connectors([{"type": "plex", "base_url": "http://p"}]))


# -- notification connectors ----------------------------------------------------


def _notifications(config):
    return TrangaNotificationConnectorProvider(
        T, "", config, "tranga.notification_connector"
    )


# What Tranga stores for PUT /v2/NotificationConnector/Gotify
# {url: http://gotify:80, appToken: tok, priority: 5}.
GOTIFY = {
    "name": "gotify",
    "url": "http://gotify:80/message",
    "httpMethod": "POST",
    "body": '{"message": "%text", "title": "%title", "Priority": 5}',
    "headers": {"X-Gotify-Key": "tok"},
}


@responses.activate
def test_gotify_shortcut_matches_what_tranga_stores(plan_provider):
    responses.get(NC, json=[GOTIFY])
    provider = _notifications(
        {"gotify": {"type": "gotify", "url": "http://gotify:80/", "app_token": "tok"}}
    )
    assert [r.op for r in plan_provider(provider).resources] == [Op.UNCHANGED]


@responses.activate
def test_generic_connector_is_created(plan_provider, apply_changes):
    responses.get(NC, json=[])
    create = responses.put(NC, json="hook", status=201)
    provider = _notifications(
        {
            "hook": {
                "url": "http://hook/%title",
                "body": '{"t": "%text"}',
                "headers": {"Authorization": "Bearer abc"},
            }
        }
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.CREATE]
    assert "Bearer abc" not in str(plan.resources[0].field_diffs)
    apply_changes(provider, plan)
    assert json.loads(create.calls[0].request.body) == {
        "name": "hook",
        "url": "http://hook/%title",
        "httpMethod": "POST",
        "body": '{"t": "%text"}',
        "headers": {"Authorization": "Bearer abc"},
    }


@responses.activate
def test_changed_connector_is_replaced(plan_provider, apply_changes):
    responses.get(NC, json=[GOTIFY])
    delete = responses.delete(f"{NC}/gotify")
    create = responses.put(NC, json="gotify", status=201)
    provider = _notifications(
        {"gotify": {"type": "gotify", "url": "http://gotify:80", "app_token": "new"}}
    )
    plan = plan_provider(provider)
    assert [r.op for r in plan.resources] == [Op.UPDATE]
    apply_changes(provider, plan)
    assert delete.call_count == create.call_count == 1
    body = json.loads(create.calls[0].request.body)
    assert body["headers"] == {"X-Gotify-Key": "new"}
    # delete strictly before the re-create
    methods = [c.request.method for c in responses.calls if c.request.method != "GET"]
    assert methods == ["DELETE", "PUT"]


@responses.activate
def test_unknown_notification_type_is_rejected(plan_provider):
    responses.get(NC, json=[])
    with pytest.raises(ValueError, match="unknown type"):
        plan_provider(_notifications({"x": {"type": "lunasea", "url": "http://x"}}))


@responses.activate
def test_create_is_not_retried_on_server_error(plan_provider, apply_changes):
    responses.get(FL, json=[])
    create = responses.put(FL, body="boom", status=500)
    provider = _libraries({"Comics": {"base_path": "/Comics"}})
    with pytest.raises(requests.HTTPError):
        apply_changes(provider, plan_provider(provider))
    assert create.call_count == 1
