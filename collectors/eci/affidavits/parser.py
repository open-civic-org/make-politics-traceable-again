from __future__ import annotations

import re

from collectors.eci.affidavits.schemas import (
    ExtractedDocument,
    ExtractionStatus,
    FieldStatus,
    ParsedAffidavit,
    ParsedAsset,
    ParsedCaseDeclaration,
    ParsedEducation,
    ParsedIncome,
    ParsedLiability,
    ParsedProfession,
)


class AffidavitParseError(Exception):
    pass


_SECTION_RE = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)
_KV_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_/ -]*):\s*(.*)$")


def parse_extracted_document(doc: ExtractedDocument) -> ParsedAffidavit:
    if doc.extraction_status == ExtractionStatus.OCR_REQUIRED:
        raise AffidavitParseError("OCR_REQUIRED: cannot parse without machine-readable text")
    if doc.extraction_status != ExtractionStatus.TEXT_EXTRACTED:
        raise AffidavitParseError(f"extraction failed: {doc.warnings}")

    sections = _split_sections(doc.full_text)
    meta = _kv_map(sections.get("HEADER", ""))
    candidate = meta.get("Candidate Name") or meta.get("candidate_name")
    if not candidate:
        raise AffidavitParseError("candidate name missing from HEADER")

    parsed = ParsedAffidavit(
        candidate_name_raw=candidate.strip(),
        constituency_name_raw=_opt(meta, "Constituency"),
        state_name_raw=_opt(meta, "State"),
        election_year=_int_or_none(meta.get("Election Year")),
        election_type=(meta.get("Election Type") or "LOK_SABHA").strip().upper(),
        source_candidate_id=_opt(meta, "Source Candidate Id"),
        section_status={},
        warnings=list(doc.warnings),
    )

    edu_text = sections.get("EDUCATION", "")
    if edu_text.strip():
        parsed.education = _parse_education(edu_text)
        parsed.section_status["education"] = "PARSED"
    else:
        parsed.section_status["education"] = "MISSING"

    prof_text = sections.get("PROFESSION", "")
    if prof_text.strip():
        kv = _kv_map(prof_text)
        val = kv.get("Occupation") or kv.get("Profession") or prof_text.strip().splitlines()[0]
        parsed.profession = [
            ParsedProfession(declared_value_raw=val.strip(), field_status=FieldStatus.EXACT)
        ]
        parsed.section_status["profession"] = "PARSED"
    else:
        parsed.section_status["profession"] = "MISSING"

    assets_text = sections.get("ASSETS", "")
    if assets_text.strip():
        parsed.assets = _parse_assets(assets_text)
        parsed.section_status["assets"] = "PARSED"
    else:
        parsed.section_status["assets"] = "MISSING"

    liab_text = sections.get("LIABILITIES", "")
    if liab_text.strip():
        parsed.liabilities = _parse_liabilities(liab_text)
        parsed.section_status["liabilities"] = "PARSED"
    else:
        parsed.section_status["liabilities"] = "MISSING"

    cases_text = sections.get("CRIMINAL_CASES", "")
    if "NEEDS_REVIEW" in cases_text.upper():
        parsed.section_status["criminal_cases"] = "NEEDS_REVIEW"
        parsed.warnings.append("Criminal cases section marked NEEDS_REVIEW")
        # Still try to parse clear rows
        parsed.cases = _parse_cases(cases_text)
    elif cases_text.strip():
        if re.search(r"^\s*(nil|none|no cases)\s*$", cases_text.strip(), re.I | re.M):
            parsed.section_status["criminal_cases"] = "PARSED"
            parsed.cases = []
        else:
            parsed.cases = _parse_cases(cases_text)
            parsed.section_status["criminal_cases"] = "PARSED"
    else:
        parsed.section_status["criminal_cases"] = "MISSING"

    income_text = sections.get("INCOME", "")
    if income_text.strip():
        parsed.income = _parse_income(income_text)
        parsed.section_status["income"] = "PARSED"
    else:
        parsed.section_status["income"] = "MISSING"

    return parsed


def _split_sections(text: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return {"HEADER": text}
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip().upper().replace(" ", "_")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()
    return sections


def _kv_map(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _KV_RE.match(line.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _opt(d: dict[str, str], key: str) -> str | None:
    v = d.get(key)
    return v.strip() if v and v.strip() else None


def _int_or_none(v: str | None) -> int | None:
    if not v:
        return None
    try:
        return int(str(v).strip())
    except ValueError:
        return None


def _parse_education(text: str) -> list[ParsedEducation]:
    items: list[ParsedEducation] = []
    for block in re.split(r"\n\s*-\s*", text):
        block = block.strip(" -\n")
        if not block:
            continue
        kv = _kv_map(block)
        raw = kv.get("Qualification") or kv.get("Education") or block.splitlines()[0]
        items.append(
            ParsedEducation(
                declared_value_raw=raw.strip(),
                institution_raw=_opt(kv, "Institution"),
                year_raw=_opt(kv, "Year"),
                field_status=FieldStatus.EXACT,
            )
        )
    return items


def _parse_assets(text: str) -> list[ParsedAsset]:
    items: list[ParsedAsset] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(
            r"^(TOTAL_ASSETS|MOVABLE_ASSETS|IMMOVABLE_ASSETS|OTHER)\s*:\s*(.+?)\s*\|\s*(.+)$",
            line,
            re.I,
        )
        if m:
            items.append(
                ParsedAsset(
                    asset_category=m.group(1).upper(),
                    description=m.group(2).strip(),
                    amount_raw=m.group(3).strip(),
                    field_status=FieldStatus.EXACT,
                )
            )
            continue
        m2 = re.match(r"^(TOTAL_ASSETS|MOVABLE_ASSETS|IMMOVABLE_ASSETS)\s*:\s*(.+)$", line, re.I)
        if m2:
            items.append(
                ParsedAsset(
                    asset_category=m2.group(1).upper(),
                    description=m2.group(1).replace("_", " ").title(),
                    amount_raw=m2.group(2).strip(),
                    field_status=FieldStatus.EXACT,
                )
            )
    return items


def _parse_liabilities(text: str) -> list[ParsedLiability]:
    items: list[ParsedLiability] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(TOTAL_LIABILITIES|OTHER)\s*:\s*(.+?)\s*\|\s*(.+)$", line, re.I)
        if m:
            items.append(
                ParsedLiability(
                    description=m.group(2).strip(),
                    amount_raw=m.group(3).strip(),
                    field_status=FieldStatus.EXACT,
                )
            )
            continue
        m2 = re.match(r"^(TOTAL_LIABILITIES)\s*:\s*(.+)$", line, re.I)
        if m2:
            items.append(
                ParsedLiability(
                    description="Total liabilities",
                    amount_raw=m2.group(2).strip(),
                    field_status=FieldStatus.EXACT,
                )
            )
    return items


def _parse_cases(text: str) -> list[ParsedCaseDeclaration]:
    items: list[ParsedCaseDeclaration] = []
    for block in re.split(r"\n\s*-\s*", text):
        block = block.strip(" -\n")
        if not block or "NEEDS_REVIEW" in block.upper() and "Case" not in block:
            continue
        kv = _kv_map(block)
        summary = kv.get("Summary") or kv.get("Case") or block.splitlines()[0]
        if summary.upper().startswith("NEEDS_REVIEW"):
            continue
        items.append(
            ParsedCaseDeclaration(
                case_summary=summary.strip(),
                case_number_raw=_opt(kv, "Case Number"),
                court_raw=_opt(kv, "Court"),
                act_raw=_opt(kv, "Act"),
                section_raw=_opt(kv, "Section"),
                status_raw=_opt(kv, "Status"),
                date_raw=_opt(kv, "Date"),
                field_status=FieldStatus.EXACT,
            )
        )
    return items


def _parse_income(text: str) -> list[ParsedIncome]:
    items: list[ParsedIncome] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)\s*\|\s*(.+?)\s*\|\s*(.+)$", line)
        if m:
            items.append(
                ParsedIncome(
                    description=m.group(1).strip(),
                    amount_raw=m.group(2).strip(),
                    assessment_year=m.group(3).strip(),
                    field_status=FieldStatus.EXACT,
                )
            )
    return items
