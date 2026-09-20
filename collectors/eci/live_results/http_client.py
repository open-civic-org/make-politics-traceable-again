"""Guarded HTTP client for the ECI results canary (HTTPS + host allowlist + caps)."""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_HOST = "results.eci.gov.in"
USER_AGENT = (
    "make-politics-traceable-again/0.1 "
    "(+https://github.com/open-civic-org/make-politics-traceable-again)"
)
MAX_LIVE_REQUESTS = 5
MIN_REQUEST_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 5_000_000
MAX_5XX_RETRIES = 2


class LiveAccessError(Exception):
    """Raised when live access is disabled or policy forbids a request."""


class LiveNetworkError(Exception):
    """Raised when the remote response requires stopping the canary."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        Exception.__init__(self, message)


@dataclass
class LiveResponse:
    url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str | None
    retrieved_at: datetime
    etag: str | None = None
    last_modified: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class RequestBudget:
    max_requests: int = MAX_LIVE_REQUESTS
    min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS
    requests_made: int = 0
    last_request_at: float | None = None
    spacings: list[float] = field(default_factory=list)

    def consume(self) -> None:
        if self.requests_made >= self.max_requests:
            raise LiveNetworkError(
                f"request cap reached ({self.max_requests})",
                status_code=None,
            )
        now = time.monotonic()
        if self.last_request_at is not None:
            wait = self.min_interval_seconds - (now - self.last_request_at)
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self.spacings.append(now - self.last_request_at)
        self.last_request_at = now
        self.requests_made += 1


def assert_live_enabled(enabled: bool) -> None:
    if not enabled:
        raise LiveAccessError(
            "live ECI access disabled; set MPTA_ECI_LIVE_ENABLED=true and pass --confirm-live"
        )


def validate_eci_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise LiveAccessError(f"HTTPS required: {url!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise LiveAccessError(f"missing host: {url!r}")
    try:
        ipaddress.ip_address(host)
        raise LiveAccessError(f"IP-literal URLs rejected: {url!r}")
    except ValueError:
        pass
    if host != ALLOWED_HOST:
        raise LiveAccessError(f"host not allowlisted: {host!r} (allowed: {ALLOWED_HOST})")
    return url


class EciResultsHttpClient:
    """Single-threaded HTTPS client bounded to results.eci.gov.in."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        budget: RequestBudget | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.budget = budget or RequestBudget()
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EciResultsHttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get(self, url: str) -> LiveResponse:
        validate_eci_url(url)
        self.budget.consume()
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.get(url)
            except httpx.TimeoutException as exc:
                if attempt <= MAX_5XX_RETRIES:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise LiveNetworkError(f"timeout fetching {url}") from exc

            for hop in response.history:
                loc = hop.headers.get("location")
                if loc:
                    validate_eci_url(urljoin(str(hop.url), loc))
            validate_eci_url(str(response.url))

            status = response.status_code
            if status == 429:
                retry_after = response.headers.get("Retry-After")
                raise LiveNetworkError(
                    f"429 Too Many Requests (Retry-After={retry_after!r}); stopping canary",
                    status_code=429,
                )
            if status == 403:
                raise LiveNetworkError(
                    "403 Forbidden; stopping canary (no bypass)", status_code=403
                )
            if status >= 500:
                if attempt <= MAX_5XX_RETRIES:
                    time.sleep(min(2**attempt, 8))
                    continue
                raise LiveNetworkError(
                    f"{status} from {url}; stopping after retries", status_code=status
                )

            body = response.content
            if len(body) > MAX_RESPONSE_BYTES:
                raise LiveNetworkError(
                    f"response exceeds size cap ({MAX_RESPONSE_BYTES} bytes)",
                    status_code=status,
                )

            return LiveResponse(
                url=url,
                final_url=str(response.url),
                status_code=status,
                content=body,
                content_type=response.headers.get("content-type"),
                retrieved_at=datetime.now(UTC),
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                elapsed_seconds=time.monotonic() - started,
            )
