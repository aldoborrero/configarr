import responses

from configarr.model import Op, ResourcePlan
from configarr.providers.applications import ApplicationProvider
from configarr.providers.base import Action, FieldProvider
from configarr.providers.custom_formats import CustomFormatProvider
from configarr.providers.download_clients import DownloadClientProvider
from configarr.providers.indexers import IndexerProvider
from configarr.providers.notifications import NotificationProvider
from configarr.providers.prowlarr_download_clients import ProwlarrDownloadClientProvider

COLLECTION_FIELD_PROVIDERS = [
    DownloadClientProvider,
    NotificationProvider,
    IndexerProvider,
    ApplicationProvider,
    ProwlarrDownloadClientProvider,
]


def test_collection_field_providers_are_prunable():
    # These name-keyed collections opt into --prune. Their DELETE path is verified by
    # the to_action / _apply_force_save tests below, and prune is ownership-scoped
    # (configarr.state), so only configarr-created resources are ever deleted.
    for cls in COLLECTION_FIELD_PROVIDERS:
        assert cls.prunable is True, cls


def test_custom_formats_is_prunable():
    assert CustomFormatProvider.prunable is True


class _FP(FieldProvider):
    def build_desired(self):
        return []


def test_field_provider_to_action_handles_delete():
    p = _FP("http://x", "k", {}, "radarr.download_client")
    action = p.to_action(
        ResourcePlan(kind=p.kind, key="old", op=Op.DELETE),
        current={"id": 9, "name": "old"},
        desired=None,
    )
    assert action.op is Op.DELETE
    assert action.payload == {"id": 9}


@responses.activate
def test_field_provider_apply_force_save_deletes():
    responses.delete("http://x/api/v3/downloadclient/9", status=200)
    p = _FP("http://x", "k", {}, "radarr.download_client")
    p._apply_force_save(
        "/api/v3/downloadclient", Action(op=Op.DELETE, key="old", payload={"id": 9})
    )
    deletes = [c for c in responses.calls if c.request.method == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0].request.url == "http://x/api/v3/downloadclient/9"


@responses.activate
def test_field_provider_apply_force_save_returns_service_id():
    # The runner records this id for rename-tolerant matching (create response id;
    # the known id on update; nothing on delete).
    p = _FP("http://x", "k", {}, "radarr.download_client")
    responses.post("http://x/api/v3/downloadclient", json={"id": 5}, status=201)
    assert (
        p._apply_force_save(
            "/api/v3/downloadclient",
            Action(op=Op.CREATE, key="n", payload={"name": "n"}),
        )
        == 5
    )
    responses.put("http://x/api/v3/downloadclient/7", status=200)
    assert (
        p._apply_force_save(
            "/api/v3/downloadclient", Action(op=Op.UPDATE, key="n", payload={"id": 7})
        )
        == 7
    )
    responses.delete("http://x/api/v3/downloadclient/9", status=200)
    assert (
        p._apply_force_save(
            "/api/v3/downloadclient", Action(op=Op.DELETE, key="n", payload={"id": 9})
        )
        is None
    )
