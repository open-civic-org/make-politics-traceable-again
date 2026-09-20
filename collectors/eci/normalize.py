from __future__ import annotations

from decimal import Decimal

from collectors.eci.schemas import (
    NormalizedCandidateResult,
    NormalizedConstituency,
    NormalizedElection,
    ParsedElection,
)
from packages.shared.ids import normalize_name


def normalize_election(parsed: ParsedElection) -> NormalizedElection:
    c = parsed.constituency
    candidates: list[NormalizedCandidateResult] = []
    total_votes = sum(x.votes for x in parsed.candidates if x.votes >= 0)

    for row in parsed.candidates:
        vote_share = row.vote_share_percent
        derived = False
        if vote_share is None and total_votes > 0 and row.votes >= 0:
            # Only derive when a clear denominator exists (sum of reported votes).
            vote_share = (Decimal(row.votes) * Decimal("100") / Decimal(total_votes)).quantize(
                Decimal("0.0001")
            )
            derived = True
        candidates.append(
            NormalizedCandidateResult(
                candidate_name_raw=row.candidate_name,
                candidate_name_normalized=normalize_name(row.candidate_name),
                party_name_raw=row.party_name,
                party_name_normalized=normalize_name(row.party_name),
                party_abbreviation=row.party_abbreviation,
                votes=row.votes,
                vote_share=vote_share,
                vote_share_derived=derived,
                rank=row.rank,
                result=row.result,
                source_candidate_id=row.source_candidate_id,
            )
        )

    return NormalizedElection(
        election_type=parsed.election_type,
        election_year=parsed.year,
        election_date=parsed.election_date,
        source_election_id=parsed.eci_election_id,
        constituency=NormalizedConstituency(
            name_raw=c.name,
            name_normalized=normalize_name(c.name),
            source_identifier=c.eci_constituency_code,
            state_name_raw=c.state_name,
            state_name_normalized=normalize_name(c.state_name),
            state_code=c.state_code,
            constituency_type=c.constituency_type,
        ),
        candidates=candidates,
    )
