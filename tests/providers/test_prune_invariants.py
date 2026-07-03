import responses

from configarr.model import Op, ResourcePlan
from configarr.providers.applications import ApplicationProvider
from configarr.providers.base import Action, FieldProvider
from configarr.providers.custom_formats import CustomFormatProvider
from configarr.providers.download_clients import DownloadClientProvider
from configarr.providers.indexers import IndexerProvider
from configarr.providers.notifications import NotificationProvider
from configarr.providers.prowlarr_download_clients import ProwlarrDownloadClientProvider

FIELD_PROVIDERS = [
    DownloadClientProvider,
    NotificationProvider,
    IndexerProvider,
    ApplicationProvider,
    ProwlarrDownloadClientProvider,
]


def test_field_providers_stay_non_prunable():
    # Locks the invariant: FieldProviders don't opt into --prune. If one ever does,
    # its to_action/_apply_force_save DELETE path (below) must be verified first.
    for cls in FIELD_PROVIDERS:
        assert cls.prunable is False, cls


def test_only_custom_formats_opts_into_prune():
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
