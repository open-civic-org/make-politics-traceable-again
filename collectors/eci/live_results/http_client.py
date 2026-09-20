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
MAX_REDIRECT_HOPS = 5
STREAM_CHUNK_SIZE = 64 * 1024


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
        """Reserve one outbound HTTP attempt (initial, redirect, or retry)."""
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


def _read_body_limited(response: httpx.Response) -> bytes:
    """Stream the body; reject oversized Content-Length or cumulative bytes."""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > MAX_RESPONSE_BYTES:
            response.close()
            raise LiveNetworkError(
                f"Content-Length {declared} exceeds size cap ({MAX_RESPONSE_BYTES} bytes)",
                status_code=response.status_code,
            )

    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise LiveNetworkError(
                    f"response exceeds size cap ({MAX_RESPONSE_BYTES} bytes)",
                    status_code=response.status_code,
                )
            chunks.append(chunk)
    finally:
        response.close()
    return b"".join(chunks)


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
            follow_redirects=False,
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
        started = time.monotonic()
        current = url
        redirect_chain: list[str] = []
        redirect_hops = 0
        server_error_retries = 0
        timeout_retries = 0

        while True:
            self.budget.consume()
            try:
                request = self._client.build_request("GET", current)
                response = self._client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                timeout_retries += 1
                if timeout_retries <= MAX_5XX_RETRIES:
                    continue
                raise LiveNetworkError(f"timeout fetching {current}") from exc

            status = response.status_code
            # Capture headers before body stream is closed.
            content_type = response.headers.get("content-type")
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")

            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise LiveNetworkError(
                        f"redirect {status} without Location from {current}",
                        status_code=status,
                    )
                next_url = urljoin(current, location)
                # Validate BEFORE any request to the destination.
                validate_eci_url(next_url)
                redirect_hops += 1
                if redirect_hops > MAX_REDIRECT_HOPS:
                    raise LiveNetworkError(
                        f"redirect hop limit exceeded ({MAX_REDIRECT_HOPS})",
                        status_code=status,
                    )
                if next_url == current or next_url in redirect_chain:
                    raise LiveNetworkError(
                        f"redirect loop detected at {next_url!r}",
                        status_code=status,
                    )
                redirect_chain.append(current)
                current = next_url
                server_error_retries = 0
                timeout_retries = 0
                continue

            if status == 429:
                retry_after = response.headers.get("Retry-After")
                response.close()
                raise LiveNetworkError(
                    f"429 Too Many Requests (Retry-After={retry_after!r}); stopping canary",
                    status_code=429,
                )
            if status == 403:
                response.close()
                raise LiveNetworkError(
                    "403 Forbidden; stopping canary (no bypass)", status_code=403
                )
            if status >= 500:
                response.close()
                server_error_retries += 1
                if server_error_retries <= MAX_5XX_RETRIES:
                    continue
                raise LiveNetworkError(
                    f"{status} from {current}; stopping after retries",
                    status_code=status,
                )

            body = _read_body_limited(response)
            return LiveResponse(
                url=url,
                final_url=current,
                status_code=status,
                content=body,
                content_type=content_type,
                retrieved_at=datetime.now(UTC),
                etag=etag,
                last_modified=last_modified,
                elapsed_seconds=time.monotonic() - started,
            )
