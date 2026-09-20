"""SQLAlchemy ORM models for core entities."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from packages.db.base import Base
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


class SourceDocument(Base):
    __tablename__ = "source_document"

    source_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_authority: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    document_title: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    archived_path: Mapped[str | None] = mapped_column(Text)
    collector_name: Mapped[str | None] = mapped_column(String(128))
    collector_version: Mapped[str | None] = mapped_column(String(32))
    parser_version: Mapped[str | None] = mapped_column(String(32))
    git_commit_sha: Mapped[str | None] = mapped_column(String(40))
    extraction_method: Mapped[str | None] = mapped_column(String(64))
    extraction_confidence: Mapped[str | None] = mapped_column(String(32))
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNVERIFIED"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Party(Base):
    __tablename__ = "party"

    party_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    abbreviation: Mapped[str | None] = mapped_column(String(64))
    official_name: Mapped[str | None] = mapped_column(String(512))
    registration_status: Mapped[str | None] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    source: Mapped[SourceDocument | None] = relationship()


class State(Base):
    __tablename__ = "state"

    state_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    code: Mapped[str | None] = mapped_column(String(8), unique=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class District(Base):
    __tablename__ = "district"

    district_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state_id: Mapped[str] = mapped_column(ForeignKey("state.state_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))

    state: Mapped[State] = relationship()


class ParliamentaryConstituency(Base):
    __tablename__ = "parliamentary_constituency"

    pc_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state_id: Mapped[str] = mapped_column(ForeignKey("state.state_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    eci_code: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))

    state: Mapped[State] = relationship()


class AssemblyConstituency(Base):
    __tablename__ = "assembly_constituency"

    ac_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state_id: Mapped[str] = mapped_column(ForeignKey("state.state_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    eci_code: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))

    state: Mapped[State] = relationship()


class Municipality(Base):
    __tablename__ = "municipality"

    municipality_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("district.district_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class MunicipalWard(Base):
    __tablename__ = "municipal_ward"

    ward_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    municipality_id: Mapped[str] = mapped_column(
        ForeignKey("municipality.municipality_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    ward_number: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class Block(Base):
    __tablename__ = "block"

    block_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    district_id: Mapped[str] = mapped_column(ForeignKey("district.district_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class GramPanchayat(Base):
    __tablename__ = "gram_panchayat"

    gram_panchayat_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    block_id: Mapped[str] = mapped_column(ForeignKey("block.block_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class Village(Base):
    __tablename__ = "village"

    village_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    gram_panchayat_id: Mapped[str] = mapped_column(
        ForeignKey("gram_panchayat.gram_panchayat_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class Person(Base):
    __tablename__ = "person"

    person_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(Text)
    current_party_id: Mapped[str | None] = mapped_column(ForeignKey("party.party_id"))
    current_office: Mapped[str | None] = mapped_column(String(128))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    current_party: Mapped[Party | None] = relationship()
    aliases: Mapped[list[PersonAlias]] = relationship(back_populates="person")


class PersonAlias(Base):
    __tablename__ = "person_alias"
    __table_args__ = (UniqueConstraint("person_id", "alias", "language", name="uq_person_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16))
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))

    person: Mapped[Person] = relationship(back_populates="aliases")


class Office(Base):
    __tablename__ = "office"

    office_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    level: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))


class OfficeTerm(Base):
    __tablename__ = "office_term"

    office_term_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    office_id: Mapped[str] = mapped_column(ForeignKey("office.office_id"), nullable=False)
    party_id: Mapped[str | None] = mapped_column(ForeignKey("party.party_id"))
    state_id: Mapped[str | None] = mapped_column(ForeignKey("state.state_id"))
    constituency_pc_id: Mapped[str | None] = mapped_column(
        ForeignKey("parliamentary_constituency.pc_id")
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    person: Mapped[Person] = relationship()
    office: Mapped[Office] = relationship()
    party: Mapped[Party | None] = relationship()
    state: Mapped[State | None] = relationship()
    constituency: Mapped[ParliamentaryConstituency | None] = relationship()
    source: Mapped[SourceDocument] = relationship()


class Election(Base):
    __tablename__ = "election"

    election_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    election_type: Mapped[str] = mapped_column(String(64), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    election_date: Mapped[date | None] = mapped_column(Date)
    state_id: Mapped[str | None] = mapped_column(ForeignKey("state.state_id"))
    constituency_pc_id: Mapped[str | None] = mapped_column(
        ForeignKey("parliamentary_constituency.pc_id")
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    state: Mapped[State | None] = relationship()
    constituency: Mapped[ParliamentaryConstituency | None] = relationship()
    source: Mapped[SourceDocument] = relationship()


class Candidacy(Base):
    __tablename__ = "candidacy"
    __table_args__ = (
        UniqueConstraint("person_id", "election_id", name="uq_candidacy_person_election"),
    )

    candidacy_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    election_id: Mapped[str] = mapped_column(ForeignKey("election.election_id"), nullable=False)
    party_id: Mapped[str | None] = mapped_column(ForeignKey("party.party_id"))
    candidate_name_as_published: Mapped[str] = mapped_column(String(256), nullable=False)
    nomination_status: Mapped[str] = mapped_column(String(64), nullable=False, default="ACCEPTED")
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    person: Mapped[Person] = relationship()
    election: Mapped[Election] = relationship()
    party: Mapped[Party | None] = relationship()
    source: Mapped[SourceDocument] = relationship()
    result: Mapped[ElectionResult | None] = relationship(back_populates="candidacy", uselist=False)
    source_identifiers: Mapped[list[CandidacySourceIdentifier]] = relationship(
        back_populates="candidacy"
    )


class CandidacySourceIdentifier(Base):
    """
    External source identifier attached to a candidacy (never an internal Person PK).

    Uniqueness scope (documented):
      (source_authority, source_system, identifier_type, external_value_raw, election_id)
    identifies at most one candidacy. ECI IDs are not assumed globally permanent across
    elections; election_id is part of the unique key.
    """

    __tablename__ = "candidacy_source_identifier"
    __table_args__ = (
        UniqueConstraint(
            "source_authority",
            "source_system",
            "identifier_type",
            "external_value_raw",
            "election_id",
            name="uq_csi_authority_system_type_value_election",
        ),
    )

    identifier_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    candidacy_id: Mapped[str] = mapped_column(ForeignKey("candidacy.candidacy_id"), nullable=False)
    election_id: Mapped[str] = mapped_column(ForeignKey("election.election_id"), nullable=False)
    source_authority: Mapped[str] = mapped_column(String(128), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_value_raw: Mapped[str] = mapped_column(String(256), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidacy: Mapped[Candidacy] = relationship(back_populates="source_identifiers")
    election: Mapped[Election] = relationship()
    source: Mapped[SourceDocument] = relationship()


class ElectionResult(Base):
    __tablename__ = "election_result"

    result_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    candidacy_id: Mapped[str] = mapped_column(
        ForeignKey("candidacy.candidacy_id"), nullable=False, unique=True
    )
    votes_received: Mapped[int | None] = mapped_column(BigInteger)
    vote_share: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    result: Mapped[str] = mapped_column(String(64), nullable=False)
    winning_margin: Mapped[int | None] = mapped_column(BigInteger)
    rank: Mapped[int | None] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    candidacy: Mapped[Candidacy] = relationship(back_populates="result")
    source: Mapped[SourceDocument] = relationship()


class Affidavit(Base):
    __tablename__ = "affidavit"

    affidavit_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    election_id: Mapped[str | None] = mapped_column(ForeignKey("election.election_id"))
    candidacy_id: Mapped[str | None] = mapped_column(ForeignKey("candidacy.candidacy_id"))
    original_document_url: Mapped[str | None] = mapped_column(Text)
    local_archive_path: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_authority: Mapped[str] = mapped_column(String(128), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)
    extraction_status: Mapped[str | None] = mapped_column(String(32))
    parse_status: Mapped[str | None] = mapped_column(String(32))
    parser_version: Mapped[str | None] = mapped_column(String(64))

    person: Mapped[Person] = relationship()
    election: Mapped[Election | None] = relationship()
    source: Mapped[SourceDocument] = relationship()
    education_declarations: Mapped[list[EducationDeclaration]] = relationship(
        back_populates="affidavit"
    )
    profession_declarations: Mapped[list[ProfessionDeclaration]] = relationship(
        back_populates="affidavit"
    )
    asset_declarations: Mapped[list[AssetDeclaration]] = relationship(back_populates="affidavit")
    liability_declarations: Mapped[list[LiabilityDeclaration]] = relationship(
        back_populates="affidavit"
    )
    criminal_case_declarations: Mapped[list[CriminalCaseDeclaration]] = relationship(
        back_populates="affidavit"
    )
    income_declarations: Mapped[list[IncomeDeclaration]] = relationship(back_populates="affidavit")


class EducationDeclaration(Base):
    __tablename__ = "education_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    declared_education: Mapped[str] = mapped_column(Text, nullable=False)
    declared_value_raw: Mapped[str | None] = mapped_column(Text)
    normalized_level: Mapped[str | None] = mapped_column(String(64))
    institution_raw: Mapped[str | None] = mapped_column(Text)
    year_raw: Mapped[str | None] = mapped_column(String(32))
    field_status: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="education_declarations")


class ProfessionDeclaration(Base):
    __tablename__ = "profession_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    declared_profession: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="profession_declarations")


class AssetDeclaration(Base):
    __tablename__ = "asset_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    asset_category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    declared_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_raw: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(8), default="INR")
    field_status: Mapped[str | None] = mapped_column(String(32))
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="asset_declarations")


class LiabilityDeclaration(Base):
    __tablename__ = "liability_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    declared_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_raw: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(8), default="INR")
    field_status: Mapped[str | None] = mapped_column(String(32))
    is_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="liability_declarations")


class CriminalCaseDeclaration(Base):
    __tablename__ = "criminal_case_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    case_summary: Mapped[str] = mapped_column(Text, nullable=False)
    disposition: Mapped[str] = mapped_column(String(64), nullable=False, default="DECLARED_PENDING")
    ipc_sections: Mapped[str | None] = mapped_column(Text)
    case_number_raw: Mapped[str | None] = mapped_column(Text)
    court_raw: Mapped[str | None] = mapped_column(Text)
    act_raw: Mapped[str | None] = mapped_column(Text)
    section_raw: Mapped[str | None] = mapped_column(Text)
    status_raw: Mapped[str | None] = mapped_column(Text)
    date_raw: Mapped[str | None] = mapped_column(String(64))
    field_status: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="criminal_case_declarations")


class IncomeDeclaration(Base):
    __tablename__ = "income_declaration"

    declaration_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    affidavit_id: Mapped[str] = mapped_column(ForeignKey("affidavit.affidavit_id"), nullable=False)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.person_id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    declared_value_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_raw: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(8), default="INR")
    field_status: Mapped[str | None] = mapped_column(String(32))
    assessment_year: Mapped[str | None] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)

    affidavit: Mapped[Affidavit] = relationship(back_populates="income_declarations")


class CollectorRun(Base):
    __tablename__ = "collector_run"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    collector_name: Mapped[str] = mapped_column(String(128), nullable=False)
    collector_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    source: Mapped[str | None] = mapped_column(Text)
    git_commit_sha: Mapped[str | None] = mapped_column(String(40))
    git_dirty: Mapped[bool | None] = mapped_column(Boolean)
    artifacts_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifacts_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_parsed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewItem(Base):
    __tablename__ = "review_item"

    review_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("source_document.source_id"))
    affidavit_id: Mapped[str | None] = mapped_column(ForeignKey("affidavit.affidavit_id"))
    archived_path: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EciElectionResultSourceRecord(Base):
    """Staging row for ECI Statistical Report 33 (and similar) workbook imports.

    Read-only identity link to candidacy when exactly one match exists.
    Never mutates Person / Candidacy / ElectionResult.
    """

    __tablename__ = "eci_election_result_source_record"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "sheet_name",
            "source_row_number",
            name="uq_eci_stat_source_sheet_row",
        ),
        Index("ix_eci_stat_election_year_type", "election_year", "election_type"),
        Index("ix_eci_stat_identity_status", "identity_status"),
        Index("ix_eci_stat_source_sha256", "source_sha256"),
    )

    record_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("source_document.source_id"), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report_number: Mapped[str] = mapped_column(String(32), nullable=False)
    report_title: Mapped[str] = mapped_column(String(256), nullable=False)
    election_type: Mapped[str] = mapped_column(String(64), nullable=False)
    election_year: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state_raw: Mapped[str] = mapped_column(Text, nullable=False)
    state_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    constituency_number_raw: Mapped[str | None] = mapped_column(String(64))
    constituency_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    constituency_name_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    candidate_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_name_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    party_name_raw: Mapped[str] = mapped_column(Text, nullable=False)
    party_name_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    gender_raw: Mapped[str | None] = mapped_column(String(64))
    age_raw: Mapped[str | None] = mapped_column(String(64))
    category_raw: Mapped[str | None] = mapped_column(String(64))
    symbol_raw: Mapped[str | None] = mapped_column(Text)
    votes_raw: Mapped[str | None] = mapped_column(Text)
    votes_value: Mapped[int | None] = mapped_column(BigInteger)
    vote_share_raw: Mapped[str | None] = mapped_column(Text)
    vote_share_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    votes_general_raw: Mapped[str | None] = mapped_column(Text)
    votes_general_value: Mapped[int | None] = mapped_column(BigInteger)
    votes_postal_raw: Mapped[str | None] = mapped_column(Text)
    votes_postal_value: Mapped[int | None] = mapped_column(BigInteger)
    total_electors_raw: Mapped[str | None] = mapped_column(Text)
    total_electors_value: Mapped[int | None] = mapped_column(BigInteger)
    valid_votes_raw: Mapped[str | None] = mapped_column(Text)
    valid_votes_value: Mapped[int | None] = mapped_column(BigInteger)
    total_votes_polled_raw: Mapped[str | None] = mapped_column(Text)
    total_votes_polled_value: Mapped[int | None] = mapped_column(BigInteger)
    result_raw: Mapped[str | None] = mapped_column(String(64))
    result_normalized: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    rank: Mapped[int | None] = mapped_column(Integer)
    source_candidate_id: Mapped[str | None] = mapped_column(String(256))
    identity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_candidacy_id: Mapped[str | None] = mapped_column(ForeignKey("candidacy.candidacy_id"))
    identity_notes: Mapped[str | None] = mapped_column(Text)
    row_status: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    collector_version: Mapped[str] = mapped_column(String(64), nullable=False)
    git_commit_sha: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped[SourceDocument] = relationship()
    identity_candidacy: Mapped[Candidacy | None] = relationship()
