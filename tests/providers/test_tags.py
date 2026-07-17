import pytest
import responses

from configarr.providers.base import HttpProvider
from configarr.providers.indexers import IndexerProvider

BASE = "http://svc.test"


class _P(HttpProvider):
    """Minimal concrete provider to exercise the shared tag resolver."""

    def __init__(self, kind: str = "radarr.download_client") -> None:
        super().__init__(BASE, "k")
        self.kind = kind


@responses.activate
def test_resolves_labels_and_passes_ints_through():
    responses.get(
        f"{BASE}/api/v3/tag",
        json=[{"id": 1, "label": "hd"}, {"id": 2, "label": "uhd"}],
    )
    assert _P()._resolve_tags(["hd", 5, "uhd"]) == [1, 5, 2]


@responses.activate
def test_tag_map_fetched_once():
    responses.get(f"{BASE}/api/v3/tag", json=[{"id": 1, "label": "hd"}])
    p = _P()
    p._resolve_tags(["hd"])
    p._resolve_tags(["hd"])
    assert len([c for c in responses.calls if c.request.url.endswith("/tag")]) == 1


@responses.activate
def test_unknown_label_raises_with_service():
    responses.get(f"{BASE}/api/v3/tag", json=[{"id": 1, "label": "hd"}])
    with pytest.raises(ValueError, match="unknown tag label 'nope' on sonarr"):
        _P(kind="sonarr.indexer")._resolve_tags(["nope"])


def test_no_labels_skips_the_tag_fetch():
    # Integer-only / empty tag lists never hit the network (no responses mock set).
    assert _P()._resolve_tags(None) == []
    assert _P()._resolve_tags([]) == []
    assert _P()._resolve_tags([3, 4]) == [3, 4]


def test_bool_and_bad_type_rejected():
    p = _P()
    with pytest.raises(ValueError, match="invalid tag"):
        p._resolve_tags([True])
    with pytest.raises(ValueError, match="invalid tag"):
        p._resolve_tags([1.5])


def test_prowlarr_uses_v1_tag_path():
    assert IndexerProvider._tag_path == "/api/v1/tag"
    assert HttpProvider._tag_path == "/api/v3/tag"
