from __future__ import annotations

import re

from collectors.eci.affidavits.currency import AmountParseStatus, parse_indian_amount
from collectors.eci.affidavits.schemas import (
    CaseStatus,
    EducationLevel,
    FieldStatus,
    NormalizedAffidavit,
    NormalizedAsset,
    NormalizedCaseDeclaration,
    NormalizedEducation,
    NormalizedIncome,
    NormalizedLiability,
    NormalizedProfession,
    ParsedAffidavit,
    ParseOutcome,
)
from packages.shared.ids import normalize_name


def normalize_affidavit(parsed: ParsedAffidavit) -> NormalizedAffidavit:
    outcome = ParseOutcome.SUCCESS
    if any(v == "NEEDS_REVIEW" for v in parsed.section_status.values()):
        outcome = ParseOutcome.PARTIAL
    if any(v == "MISSING" for v in parsed.section_status.values()):
        # missing optional sections is ok; still SUCCESS unless needs review
        pass

    education = [
        NormalizedEducation(
            declared_value_raw=e.declared_value_raw,
            normalized_level=_normalize_education_level(e.declared_value_raw),
            institution_raw=e.institution_raw,
            year_raw=e.year_raw,
            field_status=e.field_status,
            page_number=e.page_number,
        )
        for e in parsed.education
    ]

    assets: list[NormalizedAsset] = []
    for a in parsed.assets:
        amt = parse_indian_amount(a.amount_raw)
        status = _map_amount_status(amt.status, a.field_status)
        assets.append(
            NormalizedAsset(
                asset_category=a.asset_category,
                description=a.description,
                amount_raw=amt.amount_raw,
                amount_value=amt.amount_value,
                currency=amt.currency,
                field_status=status,
                is_derived=False,
                page_number=a.page_number,
            )
        )

    liabilities: list[NormalizedLiability] = []
    for li in parsed.liabilities:
        amt = parse_indian_amount(li.amount_raw)
        liabilities.append(
            NormalizedLiability(
                description=li.description,
                amount_raw=amt.amount_raw,
                amount_value=amt.amount_value,
                currency=amt.currency,
                field_status=_map_amount_status(amt.status, li.field_status),
                is_derived=False,
                page_number=li.page_number,
            )
        )

    cases = [
        NormalizedCaseDeclaration(
            case_summary=c.case_summary,
            case_number_raw=c.case_number_raw,
            court_raw=c.court_raw,
            act_raw=c.act_raw,
            section_raw=c.section_raw,
            status_raw=c.status_raw,
            normalized_status=_normalize_case_status(c.status_raw),
            date_raw=c.date_raw,
            field_status=c.field_status,
            page_number=c.page_number,
        )
        for c in parsed.cases
    ]

    profession = [
        NormalizedProfession(declared_value_raw=p.declared_value_raw, field_status=p.field_status)
        for p in parsed.profession
    ]

    income: list[NormalizedIncome] = []
    for inc in parsed.income:
        amt = parse_indian_amount(inc.amount_raw)
        income.append(
            NormalizedIncome(
                description=inc.description,
                amount_raw=amt.amount_raw,
                amount_value=amt.amount_value,
                currency=amt.currency,
                assessment_year=inc.assessment_year,
                field_status=_map_amount_status(amt.status, inc.field_status),
            )
        )

    return NormalizedAffidavit(
        candidate_name_raw=parsed.candidate_name_raw,
        candidate_name_normalized=normalize_name(parsed.candidate_name_raw),
        constituency_name_raw=parsed.constituency_name_raw,
        constituency_name_normalized=(
            normalize_name(parsed.constituency_name_raw) if parsed.constituency_name_raw else None
        ),
        state_name_raw=parsed.state_name_raw,
        state_name_normalized=(
            normalize_name(parsed.state_name_raw) if parsed.state_name_raw else None
        ),
        election_year=parsed.election_year,
        election_type=parsed.election_type,
        source_candidate_id=parsed.source_candidate_id,
        education=education,
        profession=profession,
        assets=assets,
        liabilities=liabilities,
        cases=cases,
        income=income,
        section_status=dict(parsed.section_status),
        parse_outcome=outcome,
        warnings=list(parsed.warnings),
    )


def _map_amount_status(amount_status: AmountParseStatus, field: FieldStatus) -> FieldStatus:
    if amount_status == AmountParseStatus.PARSE_FAILED:
        return FieldStatus.PARSE_FAILED
    if amount_status == AmountParseStatus.MISSING:
        return FieldStatus.MISSING
    if amount_status == AmountParseStatus.NOT_APPLICABLE:
        return FieldStatus.MISSING
    if amount_status in {AmountParseStatus.EXACT, AmountParseStatus.ZERO}:
        return FieldStatus.EXACT
    if amount_status == AmountParseStatus.NORMALIZED:
        return FieldStatus.NORMALIZED
    return field


def _normalize_education_level(raw: str) -> EducationLevel:
    t = raw.lower()
    if any(x in t for x in ("illiterate", "no formal", "uneducated")):
        return EducationLevel.NO_FORMAL_EDUCATION
    if any(x in t for x in ("ph.d", "phd", "doctorate", "doctoral")):
        return EducationLevel.DOCTORATE
    if any(
        x in t for x in ("post graduate", "postgraduate", "m.a", "m.sc", "mba", "m.tech", "ll.m")
    ):
        return EducationLevel.POSTGRADUATE
    if any(
        x in t for x in ("b.tech", "b.e", "bachelor", "graduate", "b.a", "b.sc", "ll.b", "b.com")
    ):
        return EducationLevel.GRADUATE
    if "diploma" in t:
        return EducationLevel.DIPLOMA
    if any(x in t for x in ("12th", "higher secondary", "intermediate", "hsc", "+2")):
        return EducationLevel.HIGHER_SECONDARY
    if any(x in t for x in ("10th", "matriculation", "secondary", "ssc")):
        return EducationLevel.SECONDARY
    if any(x in t for x in ("primary", "5th", "class v")):
        return EducationLevel.PRIMARY
    if any(x in t for x in ("ca ", "chartered", "professional")):
        return EducationLevel.PROFESSIONAL
    if re.search(r"[a-z]{3,}", t):
        return EducationLevel.OTHER
    return EducationLevel.UNKNOWN


def _normalize_case_status(raw: str | None) -> CaseStatus:
    if not raw:
        return CaseStatus.UNKNOWN
    t = raw.lower()
    if "acquit" in t:
        return CaseStatus.ACQUITTAL
    if "convict" in t:
        return CaseStatus.CONVICTION
    if "dismiss" in t:
        return CaseStatus.DISMISSED
    if "appeal" in t:
        return CaseStatus.APPEAL
    if "charge" in t and "fram" in t:
        return CaseStatus.CHARGE_FRAMED
    if "pending" in t:
        return CaseStatus.DECLARED_PENDING_CASE
    return CaseStatus.UNKNOWN
