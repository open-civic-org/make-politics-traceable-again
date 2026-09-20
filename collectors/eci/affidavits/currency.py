"""Indian currency / NIL parsing for affidavit financial fields."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel


class AmountParseStatus(StrEnum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    ZERO = "ZERO"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = "MISSING"
    PARSE_FAILED = "PARSE_FAILED"


class ParsedAmount(BaseModel):
    amount_raw: str | None
    amount_value: Decimal | None
    currency: str = "INR"
    status: AmountParseStatus


_NIL_RE = re.compile(r"^\s*(nil|nill|none|zero)\s*\.?$", re.IGNORECASE)
_NA_RE = re.compile(
    r"^\s*(n/?a|n\.a\.|not\s+applicable|na|-|—|–)\s*$",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*",
    re.IGNORECASE,
)
_DIGITS_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def parse_indian_amount(raw: str | None) -> ParsedAmount:
    """
    Parse Indian-formatted money strings.

    Explicit NIL → zero (ZERO). Not Applicable / dash → NOT_APPLICABLE.
    Blank → MISSING. Unparseable → PARSE_FAILED (never silent zero).
    """
    if raw is None:
        return ParsedAmount(amount_raw=None, amount_value=None, status=AmountParseStatus.MISSING)
    text = str(raw).strip()
    if not text:
        return ParsedAmount(amount_raw=raw, amount_value=None, status=AmountParseStatus.MISSING)
    if _NA_RE.match(text):
        return ParsedAmount(
            amount_raw=text, amount_value=None, status=AmountParseStatus.NOT_APPLICABLE
        )
    if _NIL_RE.match(text):
        return ParsedAmount(
            amount_raw=text, amount_value=Decimal("0"), status=AmountParseStatus.ZERO
        )

    cleaned = _CURRENCY_RE.sub("", text)
    cleaned = cleaned.replace(",", "").replace(" ", "")
    # Keep only first number-like token
    match = _DIGITS_RE.search(cleaned.replace("Rs", "").replace("rs", ""))
    if not match:
        # try after stripping non-digits except dot
        digits_only = re.sub(r"[^0-9.]", "", cleaned)
        if not digits_only:
            return ParsedAmount(
                amount_raw=text, amount_value=None, status=AmountParseStatus.PARSE_FAILED
            )
        candidate = digits_only
    else:
        candidate = match.group(0)

    try:
        value = Decimal(candidate)
    except (InvalidOperation, ValueError):
        return ParsedAmount(
            amount_raw=text, amount_value=None, status=AmountParseStatus.PARSE_FAILED
        )

    if "," in text or "₹" in text or re.search(r"rs", text, re.I):
        status = AmountParseStatus.EXACT
    else:
        status = AmountParseStatus.NORMALIZED
    if value == 0 and not _NIL_RE.match(text):
        # explicit numeric zero
        status = AmountParseStatus.EXACT
    return ParsedAmount(amount_raw=text, amount_value=value, currency="INR", status=status)
