"""Layout validation and HTML parsing for archived ECI results pages."""

from __future__ import annotations

import re
from enum import StrEnum

from collectors.eci.schemas import ParsedCandidateResult, ParsedConstituency, ParsedElection
from pydantic import BaseModel, Field

PARSER_VERSION = "ECI_RESULTS_HTML_PARSER_V1"


class LayoutStatus(StrEnum):
    OK = "OK"
    LAYOUT_CHANGED = "LAYOUT_CHANGED"
    UNSUPPORTED = "UNSUPPORTED"


class LayoutValidation(BaseModel):
    status: LayoutStatus
    reasons: list[str] = Field(default_factory=list)
    title: str | None = None


_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)
_CAND_BLOCK_RE = re.compile(
    r"(?P<status>won|lost)\s*"
    r"(?P<votes>\d[\d,]*)\s*"
    r"\([^)]*\)\s*"
    r"(?P<name>[A-Z][A-Za-z .'-]+)\s*"
    r"(?P<party>[A-Za-z0-9() .'-]+)",
    re.I | re.S,
)
_CONSTITUENCY_RE = re.compile(
    r"(?:Parliamentary|Assembly)\s+Constituency\s*(?:</[^>]+>\s*)*"
    r"(?P<no>\d+)\s*[-–]\s*(?P<name>[A-Za-z0-9() .'-]+)",
    re.I | re.S,
)


def validate_layout(html: str) -> LayoutValidation:
    reasons: list[str] = []
    title_m = _TITLE_RE.search(html)
    title = title_m.group(1).strip() if title_m else None
    lower = html.lower()

    if "election commission of india" not in lower and "eci" not in lower:
        reasons.append("missing ECI branding")
    if "candidate" not in lower and "won" not in lower and "lost" not in lower:
        reasons.append("missing candidate result markers")
    if "form-20" not in lower and "returning officer" not in lower:
        # Soft signal — some pages may omit; only fail if also missing tables/markers
        if "won" not in lower:
            reasons.append("missing Form-20 / RO disclaimer and result markers")

    if reasons:
        return LayoutValidation(status=LayoutStatus.LAYOUT_CHANGED, reasons=reasons, title=title)
    return LayoutValidation(status=LayoutStatus.OK, reasons=[], title=title)


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def parse_candidateswise_html(
    html: str,
    *,
    election_type: str = "LOK_SABHA",
    election_year: int = 2024,
) -> tuple[LayoutValidation, ParsedElection | None]:
    """
    Parse archived candidateswise HTML into ParsedElection.

    Fail closed on layout change or missing geography — returns (validation, None).
    Rank is left null unless explicitly published in the source (not derived by sorting).
    """
    validation = validate_layout(html)
    if validation.status != LayoutStatus.OK:
        return validation, None

    text = _strip_tags(html)
    constituency_name: str | None = None
    constituency_no = None
    state_name: str | None = None

    cm = _CONSTITUENCY_RE.search(html) or _CONSTITUENCY_RE.search(text)
    if cm:
        constituency_no = cm.group("no")
        constituency_name = cm.group("name").strip()
    for line in text.splitlines():
        if line.startswith("(") and line.endswith(")") and len(line) < 40:
            state_name = line.strip("()")
            break

    fail_reasons: list[str] = []
    if not constituency_name:
        fail_reasons.append("constituency not extracted")
    if not state_name:
        fail_reasons.append("state not extracted")

    candidates: list[ParsedCandidateResult] = []
    for m in _CAND_BLOCK_RE.finditer(text):
        status = m.group("status").lower()
        votes = int(m.group("votes").replace(",", ""))
        name = m.group("name").strip()
        party = m.group("party").strip()
        if not name or name.lower() in {"home", "hindi", "refresh"}:
            continue
        candidates.append(
            ParsedCandidateResult(
                candidate_name=name,
                party_name=party,
                votes=votes,
                rank=None,  # never invent / derive rank as source data
                result="WON" if status == "won" else "LOST",
                source_candidate_id=None,  # never invent
            )
        )

    if not candidates:
        fail_reasons.append("no candidate rows extracted")

    if fail_reasons:
        return (
            LayoutValidation(
                status=LayoutStatus.LAYOUT_CHANGED,
                reasons=fail_reasons,
                title=validation.title,
            ),
            None,
        )

    assert constituency_name is not None
    assert state_name is not None

    parsed = ParsedElection(
        election_type=election_type,
        year=election_year,
        election_date=None,
        eci_election_id=None,
        constituency=ParsedConstituency(
            name=constituency_name,
            eci_constituency_code=constituency_no,
            state_name=state_name,
            state_code=None,
            constituency_type="PARLIAMENTARY"
            if election_type.upper() == "LOK_SABHA"
            else "ASSEMBLY",
        ),
        candidates=candidates,
    )
    return validation, parsed
