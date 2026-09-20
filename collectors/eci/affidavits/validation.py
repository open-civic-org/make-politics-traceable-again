from __future__ import annotations

from collectors.eci.affidavits.schemas import FieldStatus, NormalizedAffidavit, ParseOutcome


class AffidavitValidationError(Exception):
    pass


def validate_affidavit(normalized: NormalizedAffidavit) -> NormalizedAffidavit:
    errors: list[str] = []
    if not normalized.candidate_name_raw.strip():
        errors.append("candidate name empty")
    if normalized.election_year is not None and not (1950 <= normalized.election_year <= 2100):
        errors.append(f"unreasonable election year: {normalized.election_year}")

    for a in normalized.assets:
        if a.field_status == FieldStatus.PARSE_FAILED:
            errors.append(f"asset amount parse failed: {a.amount_raw!r}")
        if a.amount_value is not None and a.amount_value < 0:
            errors.append("negative asset amount")

    for li in normalized.liabilities:
        if li.field_status == FieldStatus.PARSE_FAILED:
            errors.append(f"liability amount parse failed: {li.amount_raw!r}")
        if li.amount_value is not None and li.amount_value < 0:
            errors.append("negative liability amount")

    # Hard failures only — PARSE_FAILED on money is reviewable as PARTIAL if other sections ok
    hard = [e for e in errors if "candidate name" in e or "election year" in e]
    if hard:
        raise AffidavitValidationError("; ".join(hard))

    if errors:
        normalized.warnings.extend(errors)
        if normalized.parse_outcome == ParseOutcome.SUCCESS:
            normalized.parse_outcome = ParseOutcome.PARTIAL

    return normalized
