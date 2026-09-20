"""Light name normalization for statistical report staging rows."""

from __future__ import annotations

from packages.shared.ids import normalize_name

__all__ = ["normalize_name", "normalize_header_key"]


def normalize_header_key(header: str) -> str:
    """Trim, collapse whitespace, lowercase for header fingerprint matching."""
    return " ".join(header.strip().split()).casefold()
