from __future__ import annotations

from decimal import Decimal

from collectors.eci.schemas import NormalizedElection


class EciValidationError(Exception):
    """Raised when normalized ECI election data fails validation rules."""


def validate_election(normalized: NormalizedElection) -> NormalizedElection:
    errors: list[str] = []

    if not (1950 <= normalized.election_year <= 2100):
        errors.append(f"unreasonable election year: {normalized.election_year}")
    if not normalized.constituency.name_raw.strip():
        errors.append("constituency name empty")
    if not normalized.constituency.state_name_raw.strip():
        errors.append("state name empty")
    if not normalized.candidates:
        errors.append("no candidates")

    rank_ones = [c for c in normalized.candidates if c.rank == 1]
    winners = [c for c in normalized.candidates if c.result == "WON"]

    for c in normalized.candidates:
        if c.votes < 0:
            errors.append(f"negative votes for {c.candidate_name_raw!r}")
        if not c.candidate_name_raw.strip():
            errors.append("empty candidate name")
        if c.vote_share is not None:
            if c.vote_share < Decimal("0") or c.vote_share > Decimal("100"):
                errors.append(
                    f"vote_share out of range for {c.candidate_name_raw!r}: {c.vote_share}"
                )

    ranks_present = any(c.rank is not None for c in normalized.candidates)
    if len(rank_ones) > 1:
        errors.append(f"multiple rank=1 candidates: {len(rank_ones)}")
    if len(winners) > 1:
        errors.append(f"multiple WON candidates: {len(winners)}")
    if (
        rank_ones
        and winners
        and rank_ones[0].candidate_name_normalized != winners[0].candidate_name_normalized
    ):
        errors.append("rank=1 candidate does not match WON result")
    # Rank is optional when the source does not publish it; only require rank=1
    # when at least one candidate carries an explicit rank.
    if winners and ranks_present and not rank_ones:
        errors.append("WON present but no rank=1")

    if errors:
        raise EciValidationError("; ".join(errors))
    return normalized
