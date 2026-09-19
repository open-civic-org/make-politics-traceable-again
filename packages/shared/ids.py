from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class IdPrefix(StrEnum):
    PERSON = "IND-PER"
    PARTY = "IND-PTY"
    SOURCE = "SRC"
    OFFICE = "IND-OFC"
    OFFICE_TERM = "IND-OTM"
    ELECTION = "IND-ELC"
    CANDIDACY = "IND-CND"
    RESULT = "IND-RES"
    AFFIDAVIT = "IND-AFD"
    STATE = "IND-ST"
    DISTRICT = "IND-DST"
    PC = "IND-PC"
    AC = "IND-AC"
    MUNICIPALITY = "IND-MUN"
    WARD = "IND-WRD"
    BLOCK = "IND-BLK"
    GRAM_PANCHAYAT = "IND-GP"
    VILLAGE = "IND-VLG"
    EDUCATION = "IND-EDU"
    PROFESSION = "IND-PRF"
    ASSET = "IND-AST"
    LIABILITY = "IND-LIA"
    CASE = "IND-CSE"
    INCOME = "IND-INC"
    COLLECTOR_RUN = "RUN"


def allocate_id(prefix: IdPrefix | str, sequence: int) -> str:
    """Format a stable public ID from a monotonic sequence number."""
    if sequence < 1:
        raise ValueError("sequence must be >= 1")
    prefix_str = prefix.value if isinstance(prefix, IdPrefix) else prefix
    return f"{prefix_str}-{sequence:08d}"


_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_name(name: str) -> str:
    """Normalize a person/party name for matching (not for display or primary keys)."""
    text = unicodedata.normalize("NFKC", name).strip().lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text
