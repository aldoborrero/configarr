"""Unit tests for the shared HttpProvider base (session/X-Api-Key + HTTP helpers).

These lock the transport behaviour that every *arr provider now inherits instead
of repeating: the API-key header, base-url joining, and ``raise_for_status()`` on
each verb wrapper.
"""

import pytest
import requests
import responses

from configarr.providers.base import HttpProvider

BASE = "http://svc.test"


class _Probe(HttpProvider):
    """Minimal concrete provider exposing the protected HTTP helpers."""

    kind = "probe"


def _probe(base_url=BASE):
    return _Probe(base_url, api_key="secret")


def test_base_url_trailing_slash_stripped_and_url_joins():
    p = _probe(base_url=f"{BASE}/")
    assert p.base_url == BASE
    assert p._url("/api/v3/thing") == f"{BASE}/api/v3/thing"


def test_session_carries_api_key_header():
    p = _probe()
    assert p._session.headers["X-Api-Key"] == "secret"


@responses.activate
def test_get_returns_response_and_sends_api_key():
    responses.get(f"{BASE}/api/v3/thing", json=[{"id": 1}])
    p = _probe()
    resp = p._get("/api/v3/thing")
    assert resp.json() == [{"id": 1}]
    assert responses.calls[0].request.headers["X-Api-Key"] == "secret"


@responses.activate
def test_post_put_delete_send_payload_to_joined_url():
    responses.post(f"{BASE}/api/v3/thing", json={"id": 1})
    responses.put(f"{BASE}/api/v3/thing/1", json={"id": 1})
    responses.delete(f"{BASE}/api/v3/thing/1")
    p = _probe()
    p._post("/api/v3/thing", json={"name": "a"})
    p._put("/api/v3/thing/1", json={"name": "b"})
    p._delete("/api/v3/thing/1")
    assert responses.calls[0].request.body == b'{"name": "a"}'
    assert responses.calls[1].request.body == b'{"name": "b"}'
    assert responses.calls[2].request.method == "DELETE"


@responses.activate
@pytest.mark.parametrize(
    "call",
    [
        lambda p: p._get("/api/v3/thing"),
        lambda p: p._post("/api/v3/thing", json={}),
        lambda p: p._put("/api/v3/thing", json={}),
        lambda p: p._delete("/api/v3/thing"),
    ],
)
def test_helpers_raise_for_status_on_error(call):
    responses.get(f"{BASE}/api/v3/thing", status=500)
    responses.post(f"{BASE}/api/v3/thing", status=500)
    responses.put(f"{BASE}/api/v3/thing", status=500)
    responses.delete(f"{BASE}/api/v3/thing", status=500)
    with pytest.raises(requests.HTTPError):
        call(_probe())
