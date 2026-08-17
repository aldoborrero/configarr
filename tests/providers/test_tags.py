import pytest
import responses

from configarr.providers.base import HttpProvider
from configarr.providers.prowlarr.indexers import IndexerProvider

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
def test_unknown_label_warns_and_is_kept_in_plan_mode(caplog):
    # Read-only plan (the default): a missing label is warned about and kept as its
    # label (not created, never errors) so the plan's tag set stays the same length
    # as what apply will write.
    import logging

    responses.get(f"{BASE}/api/v3/tag", json=[{"id": 1, "label": "hd"}])
    with caplog.at_level(logging.WARNING, logger="configarr.providers"):
        out = _P(kind="sonarr.indexer")._resolve_tags(["hd", "nope"])
    assert out == [1, "nope"]  # 'nope' kept as its label, not dropped
    assert "will be created on apply" in caplog.text
    assert [c for c in responses.calls if c.request.method == "POST"] == []


@responses.activate
def test_unknown_label_created_on_apply():
    responses.get(f"{BASE}/api/v3/tag", json=[{"id": 1, "label": "hd"}])
    responses.post(f"{BASE}/api/v3/tag", json={"id": 9, "label": "new"}, status=201)
    p = _P()
    p._create_missing_tags = True  # the runner sets this on the apply path
    assert p._resolve_tags(["hd", "new"]) == [1, 9]


@responses.activate
def test_created_tag_is_cached():
    responses.get(f"{BASE}/api/v3/tag", json=[])
    responses.post(f"{BASE}/api/v3/tag", json={"id": 9, "label": "new"}, status=201)
    p = _P()
    p._create_missing_tags = True
    p._resolve_tags(["new"])
    p._resolve_tags(["new"])  # second time uses the cache, no second POST
    assert len([c for c in responses.calls if c.request.method == "POST"]) == 1


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
