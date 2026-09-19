from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from collectors.base.artifacts import ArchivedArtifact
from collectors.eci.schemas import ParsedCandidateResult, ParsedConstituency, ParsedElection


class EciParseError(Exception):
    pass


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EciParseError(f"invalid decimal: {value!r}") from exc


def parse_eci_result_json(data: dict[str, Any]) -> ParsedElection:
    try:
        election = data["election"]
        constituency = data["constituency"]
        candidates_raw = data["candidates"]
    except KeyError as exc:
        raise EciParseError(f"missing required key: {exc}") from exc

    election_date = None
    if election.get("electionDate"):
        election_date = date.fromisoformat(str(election["electionDate"]))

    parsed_candidates: list[ParsedCandidateResult] = []
    for row in candidates_raw:
        name = str(row.get("candidateName") or "").strip()
        party = str(row.get("partyName") or "").strip()
        if not name:
            raise EciParseError("candidateName is empty")
        if "votes" not in row:
            raise EciParseError(f"votes missing for candidate {name!r}")
        parsed_candidates.append(
            ParsedCandidateResult(
                candidate_name=name,
                party_name=party or "UNKNOWN",
                party_abbreviation=(
                    str(row["partyAbbreviation"]).strip() if row.get("partyAbbreviation") else None
                ),
                votes=int(row["votes"]),
                vote_share_percent=_decimal_or_none(row.get("voteSharePercent")),
                rank=int(row["rank"]) if row.get("rank") is not None else None,
                result=str(row["result"]).strip().upper() if row.get("result") else None,
            )
        )

    return ParsedElection(
        election_type=str(election["electionType"]).strip().upper(),
        year=int(election["year"]),
        election_date=election_date,
        eci_election_id=str(election["eciElectionId"]).strip()
        if election.get("eciElectionId")
        else None,
        constituency=ParsedConstituency(
            name=str(constituency["name"]).strip(),
            eci_constituency_code=(
                str(constituency["eciConstituencyCode"]).strip()
                if constituency.get("eciConstituencyCode")
                else None
            ),
            state_name=str(constituency["stateName"]).strip(),
            state_code=str(constituency["stateCode"]).strip()
            if constituency.get("stateCode")
            else None,
            constituency_type=str(constituency.get("constituencyType") or "PARLIAMENTARY")
            .strip()
            .upper(),
        ),
        candidates=parsed_candidates,
    )


def parse_archived_payload(artifact: ArchivedArtifact) -> ParsedElection:
    path = artifact.payload_path
    if not path.is_file():
        raise EciParseError(f"payload missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EciParseError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise EciParseError("payload root must be an object")
    return parse_eci_result_json(data)


def load_fixture_bytes(fixture_path: Path) -> bytes:
    return fixture_path.read_bytes()
