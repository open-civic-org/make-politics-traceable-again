"""Add eci_election_result_source_record for Report 33 staging.

Revision ID: 005_eci_stat_report_staging
Revises: 004_candidacy_source_identifier
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_eci_stat_report_staging"
down_revision: str | None = "004_candidacy_source_identifier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eci_election_result_source_record",
        sa.Column("record_id", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("report_number", sa.String(length=32), nullable=False),
        sa.Column("report_title", sa.String(length=256), nullable=False),
        sa.Column("election_type", sa.String(length=64), nullable=False),
        sa.Column("election_year", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=128), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("state_raw", sa.Text(), nullable=False),
        sa.Column("state_normalized", sa.String(length=256), nullable=False),
        sa.Column("constituency_number_raw", sa.String(length=64), nullable=True),
        sa.Column("constituency_name_raw", sa.Text(), nullable=False),
        sa.Column("constituency_name_normalized", sa.String(length=256), nullable=False),
        sa.Column("candidate_name_raw", sa.Text(), nullable=False),
        sa.Column("candidate_name_normalized", sa.String(length=256), nullable=False),
        sa.Column("party_name_raw", sa.Text(), nullable=False),
        sa.Column("party_name_normalized", sa.String(length=256), nullable=False),
        sa.Column("gender_raw", sa.String(length=64), nullable=True),
        sa.Column("age_raw", sa.String(length=64), nullable=True),
        sa.Column("category_raw", sa.String(length=64), nullable=True),
        sa.Column("symbol_raw", sa.Text(), nullable=True),
        sa.Column("votes_raw", sa.Text(), nullable=True),
        sa.Column("votes_value", sa.BigInteger(), nullable=True),
        sa.Column("vote_share_raw", sa.Text(), nullable=True),
        sa.Column("vote_share_value", sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column("votes_general_raw", sa.Text(), nullable=True),
        sa.Column("votes_general_value", sa.BigInteger(), nullable=True),
        sa.Column("votes_postal_raw", sa.Text(), nullable=True),
        sa.Column("votes_postal_value", sa.BigInteger(), nullable=True),
        sa.Column("total_electors_raw", sa.Text(), nullable=True),
        sa.Column("total_electors_value", sa.BigInteger(), nullable=True),
        sa.Column("valid_votes_raw", sa.Text(), nullable=True),
        sa.Column("valid_votes_value", sa.BigInteger(), nullable=True),
        sa.Column("total_votes_polled_raw", sa.Text(), nullable=True),
        sa.Column("total_votes_polled_value", sa.BigInteger(), nullable=True),
        sa.Column("result_raw", sa.String(length=64), nullable=True),
        sa.Column(
            "result_normalized", sa.String(length=64), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=256), nullable=True),
        sa.Column("identity_status", sa.String(length=32), nullable=False),
        sa.Column("identity_candidacy_id", sa.String(length=32), nullable=True),
        sa.Column("identity_notes", sa.Text(), nullable=True),
        sa.Column("row_status", sa.String(length=32), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("raw_row_json", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("collector_version", sa.String(length=64), nullable=False),
        sa.Column("git_commit_sha", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["identity_candidacy_id"], ["candidacy.candidacy_id"]),
        sa.PrimaryKeyConstraint("record_id"),
        sa.UniqueConstraint(
            "source_id",
            "sheet_name",
            "source_row_number",
            name="uq_eci_stat_source_sheet_row",
        ),
    )
    op.create_index(
        "ix_eci_stat_election_year_type",
        "eci_election_result_source_record",
        ["election_year", "election_type"],
    )
    op.create_index(
        "ix_eci_stat_identity_status",
        "eci_election_result_source_record",
        ["identity_status"],
    )
    op.create_index(
        "ix_eci_stat_source_sha256",
        "eci_election_result_source_record",
        ["source_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_eci_stat_source_sha256", table_name="eci_election_result_source_record")
    op.drop_index("ix_eci_stat_identity_status", table_name="eci_election_result_source_record")
    op.drop_index("ix_eci_stat_election_year_type", table_name="eci_election_result_source_record")
    op.drop_table("eci_election_result_source_record")
