from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from collectors.eci.normalize import normalize_election
from collectors.eci.parser import parse_eci_result_json
from collectors.eci.validation import EciValidationError, validate_election

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/eci/election_results/ge2024_demo_nagar.json"
)


def test_parse_normalize_validate_fixture() -> None:
    import json

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = parse_eci_result_json(data)
    assert parsed.year == 2024
    assert len(parsed.candidates) == 5
    assert isinstance(parsed.candidates[0].votes, int)
    assert isinstance(parsed.candidates[0].vote_share_percent, Decimal)

    normalized = normalize_election(parsed)
    assert normalized.constituency.name_normalized == "demo nagar"
    assert normalized.candidates[0].candidate_name_raw == "Asha Verma"
    assert normalized.candidates[0].vote_share_derived is False

    validated = validate_election(normalized)
    assert validated.candidates[0].rank == 1
    assert validated.candidates[0].result == "WON"


def test_validation_rejects_two_winners() -> None:
    import json

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["candidates"][1]["result"] = "WON"
    data["candidates"][1]["rank"] = 1
    parsed = parse_eci_result_json(data)
    normalized = normalize_election(parsed)
    with pytest.raises(EciValidationError):
        validate_election(normalized)


def test_vote_share_derived_when_absent() -> None:
    data = {
        "election": {"electionType": "LOK_SABHA", "year": 2024},
        "constituency": {
            "name": "X",
            "stateName": "Y",
            "constituencyType": "PARLIAMENTARY",
        },
        "candidates": [
            {"candidateName": "A", "partyName": "P", "votes": 60, "rank": 1, "result": "WON"},
            {"candidateName": "B", "partyName": "Q", "votes": 40, "rank": 2, "result": "LOST"},
        ],
    }
    normalized = normalize_election(parse_eci_result_json(data))
    assert normalized.candidates[0].vote_share_derived is True
    assert normalized.candidates[0].vote_share == Decimal("60.0000")
