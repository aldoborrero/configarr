from unittest.mock import Mock

import pytest
import requests
from urllib3.util.retry import Retry

from configarr import transport as http


def test_build_session_mounts_timeout_adapter_on_both_schemes():
    s = http.build_session()
    for scheme in ("http://", "https://"):
        adapter = s.get_adapter(scheme + "x")
        assert isinstance(adapter, http.TimeoutHTTPAdapter)


def test_retry_is_exponential_with_jitter_and_honors_retry_after():
    r = http.build_retry(total=4)
    assert isinstance(r, Retry)
    assert r.total == 4
    assert r.backoff_factor == http.BACKOFF_FACTOR
    assert r.backoff_jitter == http.BACKOFF_JITTER
    assert r.respect_retry_after_header is True
    assert set(http.RETRY_STATUSES) <= set(r.status_forcelist)


def test_post_is_not_retried_but_idempotent_methods_are():
    # A create (POST) whose response was lost must not be re-sent blindly; only
    # idempotent methods retry on connection errors. urllib3's allowed_methods gates
    # error retries and excludes POST.
    r = http.build_retry()
    assert "GET" in r.allowed_methods
    assert "PUT" in r.allowed_methods
    assert "DELETE" in r.allowed_methods
    assert "POST" not in r.allowed_methods


def test_post_retries_only_on_declined_statuses():
    # POST is retried on statuses that mean the server didn't process it (429/503),
    # but not on 5xx where a create may have taken effect. Idempotent methods retry
    # on all transient statuses.
    r = http.build_retry()
    assert r.is_retry("POST", 429) is True
    assert r.is_retry("POST", 503) is True
    assert r.is_retry("POST", 500) is False
    assert r.is_retry("POST", 502) is False
    assert r.is_retry("GET", 500) is True


def test_timeout_adapter_injects_default_when_omitted(monkeypatch):
    captured = {}

    def fake_send(self, request, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)
    adapter = http.TimeoutHTTPAdapter(timeout=7.5)
    adapter.send(Mock())
    assert captured["timeout"] == 7.5


def test_timeout_adapter_respects_explicit_timeout(monkeypatch):
    captured = {}

    def fake_send(self, request, **kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_send)
    adapter = http.TimeoutHTTPAdapter(timeout=7.5)
    adapter.send(Mock(), timeout=1.0)
    assert captured["timeout"] == 1.0


@pytest.mark.parametrize(
    "env,expected",
    [("5", 5.0), ("", http.DEFAULT_TIMEOUT), ("garbage", http.DEFAULT_TIMEOUT)],
)
def test_timeout_env_override(monkeypatch, env, expected):
    monkeypatch.setenv("CONFIGARR_HTTP_TIMEOUT", env)
    s = http.build_session()
    assert s.get_adapter("https://x")._timeout == expected


def test_retries_env_override(monkeypatch):
    monkeypatch.setenv("CONFIGARR_HTTP_RETRIES", "7")
    s = http.build_session()
    assert s.get_adapter("https://x").max_retries.total == 7
