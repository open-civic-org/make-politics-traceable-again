#!/usr/bin/env python3
"""Seed 4 fictional Lok Sabha MPs for local development. Clearly marked as demo data."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from packages.db.models import (
    Affidavit,
    AssetDeclaration,
    Candidacy,
    CriminalCaseDeclaration,
    EducationDeclaration,
    Election,
    ElectionResult,
    IncomeDeclaration,
    LiabilityDeclaration,
    Office,
    OfficeTerm,
    ParliamentaryConstituency,
    Party,
    Person,
    PersonAlias,
    ProfessionDeclaration,
    SourceDocument,
    State,
)
from packages.db.session import session_scope
from packages.shared.ids import IdPrefix, allocate_id, normalize_name
from packages.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)

RETRIEVED = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)


def _source(seq: int, authority: str, stype: str, title: str, url: str) -> SourceDocument:
    return SourceDocument(
        source_id=allocate_id(IdPrefix.SOURCE, seq),
        source_authority=authority,
        source_type=stype,
        source_url=url,
        document_title=title,
        publication_date=date(2024, 6, 4),
        retrieved_at=RETRIEVED,
        content_sha256=f"{'a' * 64}" if seq == 1 else f"{seq:064x}"[:64],
        archived_path=f"tests/fixtures/demo/source_{seq}.json",
        collector_name="seed_demo",
        collector_version="0.1.0",
        parser_version="0.1.0",
        git_commit_sha="0000000",
        extraction_method="manual_seed",
        extraction_confidence="HIGH",
        verification_status="DEMO",
    )


DEMO_MPS = [
    {
        "name": "Asha Verma",
        "alias": "A. Verma",
        "party": ("People's Civic Front", "PCF"),
        "state": ("Rajasthan", "RJ"),
        "pc": "Jaipur North Demo",
        "education": "M.A. Political Science",
        "profession": "Teacher",
        "votes": 612345,
        "share": "48.2000",
        "assets": ("Movable", "Bank deposits", "2500000"),
        "liabilities": ("Home loan", "800000"),
        "case": None,
        "income": ("Salary", "900000", "2023-24"),
    },
    {
        "name": "Ravi Krishnan",
        "alias": "R. Krishnan",
        "party": ("National Development Alliance", "NDA-DEMO"),
        "state": ("Tamil Nadu", "TN"),
        "pc": "Chennai Central Demo",
        "education": "B.Tech Computer Science",
        "profession": "Software engineer",
        "votes": 501234,
        "share": "42.1000",
        "assets": ("Immovable", "Residential flat", "7500000"),
        "liabilities": ("None declared", "0"),
        "case": ("Declared pending case related to traffic offence", "DECLARED_PENDING"),
        "income": ("Professional income", "1200000", "2023-24"),
    },
    {
        "name": "Fatima Sheikh",
        "alias": "F. Sheikh",
        "party": ("Regional Unity Party", "RUP"),
        "state": ("West Bengal", "WB"),
        "pc": "Kolkata South Demo",
        "education": "LL.B.",
        "profession": "Advocate",
        "votes": 455678,
        "share": "39.5000",
        "assets": ("Movable", "Jewellery", "450000"),
        "liabilities": ("Education loan", "200000"),
        "case": None,
        "income": ("Legal practice", "1800000", "2023-24"),
    },
    {
        "name": "Harpreet Singh Gill",
        "alias": "H. S. Gill",
        "party": ("People's Civic Front", "PCF"),
        "state": ("Punjab", "PB"),
        "pc": "Amritsar Demo",
        "education": "Graduate",
        "profession": "Agriculturist",
        "votes": 398765,
        "share": "36.8000",
        "assets": ("Immovable", "Agricultural land", "15000000"),
        "liabilities": ("Farm equipment loan", "500000"),
        "case": None,
        "income": ("Agricultural income", "600000", "2023-24"),
    },
]


def seed() -> None:
    configure_logging()
    with session_scope() as session:
        existing = session.get(Person, allocate_id(IdPrefix.PERSON, 1))
        if existing is not None:
            logger.info("Demo data already present; skipping seed")
            return

        src_geo = _source(
            1, "DEMO", "SEED", "Demo geography seed", "https://example.invalid/demo/geo"
        )
        src_party = _source(
            2, "DEMO", "SEED", "Demo party seed", "https://example.invalid/demo/party"
        )
        src_election = _source(
            3,
            "DEMO",
            "SEED",
            "Demo Lok Sabha 2024 results",
            "https://example.invalid/demo/eci/2024",
        )
        src_affidavit = _source(
            4, "DEMO", "SEED", "Demo affidavits 2024", "https://example.invalid/demo/affidavit"
        )
        session.add_all([src_geo, src_party, src_election, src_affidavit])
        session.flush()

        office = Office(
            office_id=allocate_id(IdPrefix.OFFICE, 1),
            title="Lok Sabha MP",
            level="NATIONAL",
            description="Member of the Lok Sabha",
            source_id=src_geo.source_id,
        )
        session.add(office)

        parties: dict[str, Party] = {}
        states: dict[str, State] = {}
        party_seq = 1
        state_seq = 1
        pc_seq = 1
        person_seq = 1

        for mp in DEMO_MPS:
            pname, pabbr = mp["party"]
            if pname not in parties:
                parties[pname] = Party(
                    party_id=allocate_id(IdPrefix.PARTY, party_seq),
                    name=pname,
                    abbreviation=pabbr,
                    official_name=pname,
                    registration_status="DEMO",
                    source_id=src_party.source_id,
                )
                session.add(parties[pname])
                party_seq += 1

            sname, scode = mp["state"]
            if sname not in states:
                states[sname] = State(
                    state_id=allocate_id(IdPrefix.STATE, state_seq),
                    name=sname,
                    code=scode,
                    source_id=src_geo.source_id,
                )
                session.add(states[sname])
                state_seq += 1

            pc = ParliamentaryConstituency(
                pc_id=allocate_id(IdPrefix.PC, pc_seq),
                state_id=states[sname].state_id,
                name=mp["pc"],
                eci_code=f"DEMO-{pc_seq:03d}",
                source_id=src_geo.source_id,
            )
            session.add(pc)

            person = Person(
                person_id=allocate_id(IdPrefix.PERSON, person_seq),
                canonical_name=mp["name"],
                normalized_name=normalize_name(mp["name"]),
                current_party_id=parties[pname].party_id,
                current_office="Lok Sabha MP",
                is_demo=True,
            )
            session.add(person)
            session.add(
                PersonAlias(
                    person_id=person.person_id,
                    alias=mp["alias"],
                    language="en",
                    source_id=src_election.source_id,
                )
            )

            election = Election(
                election_id=allocate_id(IdPrefix.ELECTION, person_seq),
                election_type="LOK_SABHA",
                year=2024,
                election_date=date(2024, 4, 19),
                state_id=states[sname].state_id,
                constituency_pc_id=pc.pc_id,
                source_id=src_election.source_id,
            )
            session.add(election)

            candidacy = Candidacy(
                candidacy_id=allocate_id(IdPrefix.CANDIDACY, person_seq),
                person_id=person.person_id,
                election_id=election.election_id,
                party_id=parties[pname].party_id,
                candidate_name_as_published=mp["name"],
                nomination_status="ACCEPTED",
                source_id=src_election.source_id,
            )
            session.add(candidacy)
            session.add(
                ElectionResult(
                    result_id=allocate_id(IdPrefix.RESULT, person_seq),
                    candidacy_id=candidacy.candidacy_id,
                    votes_received=mp["votes"],
                    vote_share=Decimal(mp["share"]),
                    result="WON",
                    winning_margin=12000 + person_seq * 100,
                    rank=1,
                    source_id=src_election.source_id,
                )
            )

            session.add(
                OfficeTerm(
                    office_term_id=allocate_id(IdPrefix.OFFICE_TERM, person_seq),
                    person_id=person.person_id,
                    office_id=office.office_id,
                    party_id=parties[pname].party_id,
                    state_id=states[sname].state_id,
                    constituency_pc_id=pc.pc_id,
                    start_date=date(2024, 6, 24),
                    end_date=None,
                    source_id=src_election.source_id,
                )
            )

            affidavit = Affidavit(
                affidavit_id=allocate_id(IdPrefix.AFFIDAVIT, person_seq),
                person_id=person.person_id,
                election_id=election.election_id,
                original_document_url=f"https://example.invalid/demo/affidavit/{person_seq}.pdf",
                local_archive_path=f"tests/fixtures/demo/affidavit_{person_seq}.txt",
                document_sha256=f"{person_seq:064x}"[:64],
                retrieved_at=RETRIEVED,
                source_authority="DEMO",
                source_id=src_affidavit.source_id,
            )
            session.add(affidavit)

            session.add(
                EducationDeclaration(
                    declaration_id=allocate_id(IdPrefix.EDUCATION, person_seq),
                    affidavit_id=affidavit.affidavit_id,
                    person_id=person.person_id,
                    declared_education=mp["education"],
                    source_id=src_affidavit.source_id,
                )
            )
            session.add(
                ProfessionDeclaration(
                    declaration_id=allocate_id(IdPrefix.PROFESSION, person_seq),
                    affidavit_id=affidavit.affidavit_id,
                    person_id=person.person_id,
                    declared_profession=mp["profession"],
                    source_id=src_affidavit.source_id,
                )
            )
            acat, adesc, aval = mp["assets"]
            session.add(
                AssetDeclaration(
                    declaration_id=allocate_id(IdPrefix.ASSET, person_seq),
                    affidavit_id=affidavit.affidavit_id,
                    person_id=person.person_id,
                    asset_category=acat,
                    description=adesc,
                    declared_value_inr=Decimal(aval),
                    source_id=src_affidavit.source_id,
                )
            )
            ldesc, lval = mp["liabilities"]
            session.add(
                LiabilityDeclaration(
                    declaration_id=allocate_id(IdPrefix.LIABILITY, person_seq),
                    affidavit_id=affidavit.affidavit_id,
                    person_id=person.person_id,
                    description=ldesc,
                    declared_value_inr=Decimal(lval),
                    source_id=src_affidavit.source_id,
                )
            )
            idesc, ival, iyear = mp["income"]
            session.add(
                IncomeDeclaration(
                    declaration_id=allocate_id(IdPrefix.INCOME, person_seq),
                    affidavit_id=affidavit.affidavit_id,
                    person_id=person.person_id,
                    description=idesc,
                    declared_value_inr=Decimal(ival),
                    assessment_year=iyear,
                    source_id=src_affidavit.source_id,
                )
            )
            if mp["case"]:
                csum, cdisp = mp["case"]
                session.add(
                    CriminalCaseDeclaration(
                        declaration_id=allocate_id(IdPrefix.CASE, person_seq),
                        affidavit_id=affidavit.affidavit_id,
                        person_id=person.person_id,
                        case_summary=csum,
                        disposition=cdisp,
                        source_id=src_affidavit.source_id,
                    )
                )

            pc_seq += 1
            person_seq += 1

        logger.info("Seeded %s demo Lok Sabha MPs", len(DEMO_MPS))


if __name__ == "__main__":
    seed()
