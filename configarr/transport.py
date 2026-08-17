"""Shared HTTP transport: sessions with request timeouts and bounded retries.

Every provider talks to a service over ``requests``. Two failure modes were
previously unhandled: a request with no timeout can hang the whole run
indefinitely, and a single transient error (a dropped connection, a 502 from a
reverse proxy, a 503 while the service restarts) aborts the entire sync. This
module centralizes the fix so no call site has to remember it.

``build_session`` returns a ``requests.Session`` that:

- applies a default timeout to every request (overridable per call), and
- retries idempotent requests on connection errors and transient status codes
  with **exponential backoff and jitter**, honoring ``Retry-After``.

Idempotent methods (urllib3's default ``allowed_methods``:
GET/HEAD/PUT/DELETE/OPTIONS/TRACE) retry on connection/read errors and any
transient status. ``POST`` is not retried on connection/read errors — a create
whose response was lost must not be blindly re-sent — but *is* retried on the
handful of statuses that mean the server declined to process it (``429``/``503``),
where nothing was created and a retry is safe.

Defaults are overridable via the environment for slow or flaky instances:
``CONFIGARR_HTTP_TIMEOUT`` (seconds) and ``CONFIGARR_HTTP_RETRIES`` (count).
"""

from __future__ import annotations

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Connect+read timeout applied to every request that doesn't pass its own.
DEFAULT_TIMEOUT = 30.0
# Total retry attempts for a transient failure (on top of the initial request).
DEFAULT_RETRIES = 3
# Exponential base: sleeps ~ backoff_factor * 2**(n-1) seconds between tries.
BACKOFF_FACTOR = 0.5
# Random jitter (seconds, uniform 0..N) added to each backoff to avoid syncing
# retries across concurrent instances into a thundering herd.
BACKOFF_JITTER = 0.5
# Transient status codes worth retrying (rate-limit + gateway/unavailable).
RETRY_STATUSES = (429, 500, 502, 503, 504)
# Safe to retry for a POST: the server declined to process it, so nothing was
# created. 500/502/504 are excluded — a create may have taken effect before the error.
POST_RETRY_STATUSES = (429, 503)


class _PostAwareRetry(Retry):
    """Like the default Retry, but also retries POST on ``POST_RETRY_STATUSES`` (never
    on connection errors — ``allowed_methods`` excludes POST there)."""

    def is_retry(
        self, method: str, status_code: int, has_retry_after: bool = False
    ) -> bool:
        if method and method.upper() == "POST":
            return bool(self.total) and status_code in POST_RETRY_STATUSES
        return super().is_retry(method, status_code, has_retry_after)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class TimeoutHTTPAdapter(HTTPAdapter):
    """HTTPAdapter that applies a default timeout when a request omits one.

    ``requests`` defaults to no timeout, so a stalled connection hangs forever.
    Setting it on the adapter covers every call through the session without
    touching call sites, while still letting an individual request override it.
    """

    def __init__(
        self, *args: object, timeout: float = DEFAULT_TIMEOUT, **kwargs: object
    ) -> None:
        self._timeout = timeout
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def send(self, request: object, **kwargs: object) -> object:  # type: ignore[override]
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)  # type: ignore[arg-type]


def build_retry(
    total: int = DEFAULT_RETRIES,
    backoff_factor: float = BACKOFF_FACTOR,
    backoff_jitter: float = BACKOFF_JITTER,
) -> Retry:
    """A urllib3 Retry: exponential backoff + jitter, honoring ``Retry-After`` on
    rate limits; idempotent methods retry on errors and status, POST only on
    ``POST_RETRY_STATUSES``."""
    # backoff_jitter is supported at runtime (urllib3 >= 2.0) but missing from the
    # pinned type stub, so mypy flags the kwarg it can't see.
    return _PostAwareRetry(  # type: ignore[call-arg]
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        backoff_jitter=backoff_jitter,
        status_forcelist=RETRY_STATUSES,
        respect_retry_after_header=True,
        raise_on_status=False,
    )


def build_session(
    timeout: float | None = None,
    retries: int | None = None,
) -> requests.Session:
    """Return a Session with the timeout + retry adapter mounted for http/https.

    ``timeout``/``retries`` default to the module constants, themselves
    overridable via ``CONFIGARR_HTTP_TIMEOUT`` / ``CONFIGARR_HTTP_RETRIES``.
    """
    resolved_timeout = (
        timeout
        if timeout is not None
        else _float_env("CONFIGARR_HTTP_TIMEOUT", DEFAULT_TIMEOUT)
    )
    resolved_retries = (
        retries
        if retries is not None
        else _int_env("CONFIGARR_HTTP_RETRIES", DEFAULT_RETRIES)
    )
    adapter = TimeoutHTTPAdapter(
        timeout=resolved_timeout, max_retries=build_retry(total=resolved_retries)
    )
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
