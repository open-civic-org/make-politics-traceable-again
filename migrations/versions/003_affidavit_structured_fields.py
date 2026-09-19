"""Structured affidavit fields, review queue, and financial raw amounts.

Revision ID: 003_affidavit_structured_fields
Revises: 002_collector_run
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_affidavit_structured_fields"
down_revision: str | None = "002_collector_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("affidavit", sa.Column("candidacy_id", sa.String(length=32), nullable=True))
    op.add_column("affidavit", sa.Column("extraction_status", sa.String(length=32), nullable=True))
    op.add_column("affidavit", sa.Column("parse_status", sa.String(length=32), nullable=True))
    op.add_column("affidavit", sa.Column("parser_version", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_affidavit_candidacy_id", "affidavit", "candidacy", ["candidacy_id"], ["candidacy_id"]
    )

    op.add_column("education_declaration", sa.Column("declared_value_raw", sa.Text(), nullable=True))
    op.add_column("education_declaration", sa.Column("normalized_level", sa.String(64), nullable=True))
    op.add_column("education_declaration", sa.Column("institution_raw", sa.Text(), nullable=True))
    op.add_column("education_declaration", sa.Column("year_raw", sa.String(32), nullable=True))
    op.add_column("education_declaration", sa.Column("field_status", sa.String(32), nullable=True))

    for table in ("asset_declaration", "liability_declaration", "income_declaration"):
        op.add_column(table, sa.Column("amount_raw", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("currency", sa.String(8), nullable=True))
        op.add_column(table, sa.Column("field_status", sa.String(32), nullable=True))
    op.add_column(
        "asset_declaration",
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "liability_declaration",
        sa.Column("is_derived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    op.add_column("criminal_case_declaration", sa.Column("case_number_raw", sa.Text(), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("court_raw", sa.Text(), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("act_raw", sa.Text(), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("section_raw", sa.Text(), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("status_raw", sa.Text(), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("date_raw", sa.String(64), nullable=True))
    op.add_column("criminal_case_declaration", sa.Column("field_status", sa.String(32), nullable=True))

    op.create_table(
        "review_item",
        sa.Column("review_id", sa.String(32), nullable=False),
        sa.Column("review_type", sa.String(64), nullable=False),
        sa.Column("field_name", sa.String(128), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("source_id", sa.String(32), nullable=True),
        sa.Column("affidavit_id", sa.String(32), nullable=True),
        sa.Column("archived_path", sa.Text(), nullable=True),
        sa.Column("parser_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.ForeignKeyConstraint(["affidavit_id"], ["affidavit.affidavit_id"]),
        sa.PrimaryKeyConstraint("review_id"),
    )


def downgrade() -> None:
    op.drop_table("review_item")
    for col in (
        "case_number_raw",
        "court_raw",
        "act_raw",
        "section_raw",
        "status_raw",
        "date_raw",
        "field_status",
    ):
        op.drop_column("criminal_case_declaration", col)
    op.drop_column("liability_declaration", "is_derived")
    op.drop_column("asset_declaration", "is_derived")
    for table in ("asset_declaration", "liability_declaration", "income_declaration"):
        op.drop_column(table, "field_status")
        op.drop_column(table, "currency")
        op.drop_column(table, "amount_raw")
    for col in (
        "declared_value_raw",
        "normalized_level",
        "institution_raw",
        "year_raw",
        "field_status",
    ):
        op.drop_column("education_declaration", col)
    op.drop_constraint("fk_affidavit_candidacy_id", "affidavit", type_="foreignkey")
    op.drop_column("affidavit", "parser_version")
    op.drop_column("affidavit", "parse_status")
    op.drop_column("affidavit", "extraction_status")
    op.drop_column("affidavit", "candidacy_id")
