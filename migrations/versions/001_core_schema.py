"""Initial core schema: person, party, geography, office, election, affidavit, provenance.

Revision ID: 001_core_schema
Revises:
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_core_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_document",
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("source_authority", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("document_title", sa.Text(), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("archived_path", sa.Text(), nullable=True),
        sa.Column("collector_name", sa.String(length=128), nullable=True),
        sa.Column("collector_version", sa.String(length=32), nullable=True),
        sa.Column("parser_version", sa.String(length=32), nullable=True),
        sa.Column("git_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("extraction_method", sa.String(length=64), nullable=True),
        sa.Column("extraction_confidence", sa.String(length=32), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )

    op.create_table(
        "party",
        sa.Column("party_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("abbreviation", sa.String(length=64), nullable=True),
        sa.Column("official_name", sa.String(length=512), nullable=True),
        sa.Column("registration_status", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("party_id"),
    )

    op.create_table(
        "state",
        sa.Column("state_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("code", sa.String(length=8), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("state_id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "district",
        sa.Column("district_id", sa.String(length=32), nullable=False),
        sa.Column("state_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["state_id"], ["state.state_id"]),
        sa.PrimaryKeyConstraint("district_id"),
    )

    op.create_table(
        "parliamentary_constituency",
        sa.Column("pc_id", sa.String(length=32), nullable=False),
        sa.Column("state_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("eci_code", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["state_id"], ["state.state_id"]),
        sa.PrimaryKeyConstraint("pc_id"),
    )

    op.create_table(
        "assembly_constituency",
        sa.Column("ac_id", sa.String(length=32), nullable=False),
        sa.Column("state_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("eci_code", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["state_id"], ["state.state_id"]),
        sa.PrimaryKeyConstraint("ac_id"),
    )

    op.create_table(
        "municipality",
        sa.Column("municipality_id", sa.String(length=32), nullable=False),
        sa.Column("district_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["district_id"], ["district.district_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("municipality_id"),
    )

    op.create_table(
        "municipal_ward",
        sa.Column("ward_id", sa.String(length=32), nullable=False),
        sa.Column("municipality_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("ward_number", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["municipality_id"], ["municipality.municipality_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("ward_id"),
    )

    op.create_table(
        "block",
        sa.Column("block_id", sa.String(length=32), nullable=False),
        sa.Column("district_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["district_id"], ["district.district_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("block_id"),
    )

    op.create_table(
        "gram_panchayat",
        sa.Column("gram_panchayat_id", sa.String(length=32), nullable=False),
        sa.Column("block_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["block_id"], ["block.block_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("gram_panchayat_id"),
    )

    op.create_table(
        "village",
        sa.Column("village_id", sa.String(length=32), nullable=False),
        sa.Column("gram_panchayat_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["gram_panchayat_id"], ["gram_panchayat.gram_panchayat_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("village_id"),
    )

    op.create_table(
        "person",
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("canonical_name", sa.String(length=256), nullable=False),
        sa.Column("normalized_name", sa.String(length=256), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("current_party_id", sa.String(length=32), nullable=True),
        sa.Column("current_office", sa.String(length=128), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["current_party_id"], ["party.party_id"]),
        sa.PrimaryKeyConstraint("person_id"),
    )
    op.create_index("ix_person_normalized_name", "person", ["normalized_name"])

    op.create_table(
        "person_alias",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("alias", sa.String(length=256), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.person_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "alias", "language", name="uq_person_alias"),
    )

    op.create_table(
        "office",
        sa.Column("office_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("level", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("office_id"),
        sa.UniqueConstraint("title"),
    )

    op.create_table(
        "office_term",
        sa.Column("office_term_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("office_id", sa.String(length=32), nullable=False),
        sa.Column("party_id", sa.String(length=32), nullable=True),
        sa.Column("state_id", sa.String(length=32), nullable=True),
        sa.Column("constituency_pc_id", sa.String(length=32), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["constituency_pc_id"], ["parliamentary_constituency.pc_id"]),
        sa.ForeignKeyConstraint(["office_id"], ["office.office_id"]),
        sa.ForeignKeyConstraint(["party_id"], ["party.party_id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.person_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["state_id"], ["state.state_id"]),
        sa.PrimaryKeyConstraint("office_term_id"),
    )

    op.create_table(
        "election",
        sa.Column("election_id", sa.String(length=32), nullable=False),
        sa.Column("election_type", sa.String(length=64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("election_date", sa.Date(), nullable=True),
        sa.Column("state_id", sa.String(length=32), nullable=True),
        sa.Column("constituency_pc_id", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["constituency_pc_id"], ["parliamentary_constituency.pc_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["state_id"], ["state.state_id"]),
        sa.PrimaryKeyConstraint("election_id"),
    )

    op.create_table(
        "candidacy",
        sa.Column("candidacy_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("election_id", sa.String(length=32), nullable=False),
        sa.Column("party_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_name_as_published", sa.String(length=256), nullable=False),
        sa.Column("nomination_status", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["election.election_id"]),
        sa.ForeignKeyConstraint(["party_id"], ["party.party_id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.person_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("candidacy_id"),
        sa.UniqueConstraint("person_id", "election_id", name="uq_candidacy_person_election"),
    )

    op.create_table(
        "election_result",
        sa.Column("result_id", sa.String(length=32), nullable=False),
        sa.Column("candidacy_id", sa.String(length=32), nullable=False),
        sa.Column("votes_received", sa.BigInteger(), nullable=True),
        sa.Column("vote_share", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("result", sa.String(length=64), nullable=False),
        sa.Column("winning_margin", sa.BigInteger(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["candidacy_id"], ["candidacy.candidacy_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("result_id"),
        sa.UniqueConstraint("candidacy_id"),
    )

    op.create_table(
        "affidavit",
        sa.Column("affidavit_id", sa.String(length=32), nullable=False),
        sa.Column("person_id", sa.String(length=32), nullable=False),
        sa.Column("election_id", sa.String(length=32), nullable=True),
        sa.Column("original_document_url", sa.Text(), nullable=True),
        sa.Column("local_archive_path", sa.Text(), nullable=True),
        sa.Column("document_sha256", sa.String(length=64), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_authority", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["election_id"], ["election.election_id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.person_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("affidavit_id"),
    )

    for table, cols in [
        (
            "education_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("declared_education", sa.Text(), nullable=False),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
        (
            "profession_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("declared_profession", sa.Text(), nullable=False),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
        (
            "asset_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("asset_category", sa.String(length=64), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("declared_value_inr", sa.Numeric(precision=18, scale=2), nullable=True),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
        (
            "liability_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("declared_value_inr", sa.Numeric(precision=18, scale=2), nullable=True),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
        (
            "criminal_case_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("case_summary", sa.Text(), nullable=False),
                sa.Column("disposition", sa.String(length=64), nullable=False),
                sa.Column("ipc_sections", sa.Text(), nullable=True),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
        (
            "income_declaration",
            [
                sa.Column("declaration_id", sa.String(length=32), nullable=False),
                sa.Column("affidavit_id", sa.String(length=32), nullable=False),
                sa.Column("person_id", sa.String(length=32), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("declared_value_inr", sa.Numeric(precision=18, scale=2), nullable=True),
                sa.Column("assessment_year", sa.String(length=16), nullable=True),
                sa.Column("source_id", sa.String(length=32), nullable=False),
            ],
        ),
    ]:
        op.create_table(
            table,
            *cols,
            sa.ForeignKeyConstraint(["affidavit_id"], ["affidavit.affidavit_id"]),
            sa.ForeignKeyConstraint(["person_id"], ["person.person_id"]),
            sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
            sa.PrimaryKeyConstraint("declaration_id"),
        )


def downgrade() -> None:
    for table in [
        "income_declaration",
        "criminal_case_declaration",
        "liability_declaration",
        "asset_declaration",
        "profession_declaration",
        "education_declaration",
        "affidavit",
        "election_result",
        "candidacy",
        "election",
        "office_term",
        "office",
        "person_alias",
        "person",
        "village",
        "gram_panchayat",
        "block",
        "municipal_ward",
        "municipality",
        "assembly_constituency",
        "parliamentary_constituency",
        "district",
        "state",
        "party",
        "source_document",
    ]:
        op.drop_table(table)
