"""Guarded HTTPS client for official ECI statistical-report capture.

Separate from the Milestone 4 results.eci.gov.in canary client.
Allowlist is explicit hostname equality only (no broad suffix trust).
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

# Explicit approved hosts for statistical-report acquisition (not results portal).
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "www.eci.gov.in",
        "eci.gov.in",
    }
)

USER_AGENT = (
    "make-politics-traceable-again/0.1 "
    "(+https://github.com/open-civic-org/make-politics-traceable-again)"
)
MAX_HTTP_ATTEMPTS = 5
MIN_REQUEST_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_REPORT_BYTES = 50_000_000
MAX_5XX_RETRIES = 2
MAX_REDIRECT_HOPS = 5
STREAM_CHUNK_SIZE = 64 * 1024
MAX_REPORTS_PER_RUN = 1


class CaptureAccessError(Exception):
    """Policy / configuration refusal (no network should proceed)."""


class CaptureNetworkError(Exception):
    """Remote response requires stopping capture."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        Exception.__init__(self, message)


@dataclass
class CaptureResponse:
    requested_url: str
    final_url: str
    status_code: int
    content: bytes
    content_type: str | None
    content_length_header: str | None
    content_disposition: str | None
    etag: str | None
    last_modified: str | None
    retrieved_at: datetime
    requests_made: int
    spacings: list[float]


@dataclass
class RequestBudget:
    max_requests: int = MAX_HTTP_ATTEMPTS
    min_interval_seconds: float = MIN_REQUEST_INTERVAL_SECONDS
    requests_made: int = 0
    last_request_at: float | None = None
    spacings: list[float] = field(default_factory=list)

    def consume(self) -> None:
        if self.requests_made >= self.max_requests:
            raise CaptureNetworkError(
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
        raise CaptureAccessError(
            "statistical-report live capture disabled; set "
            "MPTA_ECI_STAT_REPORT_LIVE_ENABLED=true and pass --confirm-live"
        )


def validate_capture_url(url: str) -> str:
    """Validate HTTPS + allowlisted host. Reject IP literals, userinfo, http."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise CaptureAccessError(f"HTTPS required: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise CaptureAccessError(f"userinfo URLs rejected: {url!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise CaptureAccessError(f"missing host: {url!r}")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise CaptureAccessError(f"localhost rejected: {url!r}")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise CaptureAccessError(f"private/loopback IP rejected: {url!r}")
        raise CaptureAccessError(f"IP-literal URLs rejected: {url!r}")
    except ValueError:
        pass
    if host not in ALLOWED_HOSTS:
        raise CaptureAccessError(
            f"host not allowlisted: {host!r} (allowed: {sorted(ALLOWED_HOSTS)})"
        )
    return url


def _read_body_limited(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > MAX_REPORT_BYTES:
            response.close()
            raise CaptureNetworkError(
                f"Content-Length {declared} exceeds size cap ({MAX_REPORT_BYTES} bytes)",
                status_code=response.status_code,
            )

    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_SIZE):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_REPORT_BYTES:
                raise CaptureNetworkError(
                    f"response exceeds size cap ({MAX_REPORT_BYTES} bytes)",
                    status_code=response.status_code,
                )
            chunks.append(chunk)
    finally:
        response.close()
    return b"".join(chunks)


class EciStatisticalReportHttpClient:
    """Single-report HTTPS client for allowlisted ECI statistical-report hosts."""

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
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EciStatisticalReportHttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get(self, url: str) -> CaptureResponse:
        validate_capture_url(url)
        started_url = url
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
                raise CaptureNetworkError(f"timeout fetching {current}") from exc

            status = response.status_code
            content_type = response.headers.get("content-type")
            content_length_header = response.headers.get("content-length")
            content_disposition = response.headers.get("content-disposition")
            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")

            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise CaptureNetworkError(
                        f"redirect {status} without Location from {current}",
                        status_code=status,
                    )
                next_url = urljoin(current, location)
                validate_capture_url(next_url)
                redirect_hops += 1
                if redirect_hops > MAX_REDIRECT_HOPS:
                    raise CaptureNetworkError(
                        f"redirect hop limit exceeded ({MAX_REDIRECT_HOPS})",
                        status_code=status,
                    )
                if next_url == current or next_url in redirect_chain:
                    raise CaptureNetworkError(
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
                raise CaptureNetworkError(
                    f"429 Too Many Requests (Retry-After={retry_after!r}); stopping",
                    status_code=429,
                )
            if status == 403:
                response.close()
                raise CaptureNetworkError("403 Forbidden; stopping (no bypass)", status_code=403)
            if status >= 500:
                response.close()
                server_error_retries += 1
                if server_error_retries <= MAX_5XX_RETRIES:
                    continue
                raise CaptureNetworkError(
                    f"{status} from {current}; stopping after retries",
                    status_code=status,
                )
            if status != 200:
                response.close()
                raise CaptureNetworkError(
                    f"unexpected HTTP {status} from {current}",
                    status_code=status,
                )

            body = _read_body_limited(response)
            return CaptureResponse(
                requested_url=started_url,
                final_url=current,
                status_code=status,
                content=body,
                content_type=content_type,
                content_length_header=content_length_header,
                content_disposition=content_disposition,
                etag=etag,
                last_modified=last_modified,
                retrieved_at=datetime.now(UTC),
                requests_made=self.budget.requests_made,
                spacings=list(self.budget.spacings),
            )
