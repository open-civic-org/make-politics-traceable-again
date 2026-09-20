"""Guarded live ECI election-results canary (disabled by default)."""

from collectors.eci.live_results.http_client import ALLOWED_HOST, MAX_LIVE_REQUESTS

__all__ = ["ALLOWED_HOST", "MAX_LIVE_REQUESTS"]
