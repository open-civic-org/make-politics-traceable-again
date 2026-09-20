"""Add candidacy_source_identifier for external ECI IDs.

Revision ID: 004_candidacy_source_identifier
Revises: 003_affidavit_structured_fields
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_candidacy_source_identifier"
down_revision: str | None = "003_affidavit_structured_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidacy_source_identifier",
        sa.Column("identifier_id", sa.String(length=32), nullable=False),
        sa.Column("candidacy_id", sa.String(length=32), nullable=False),
        sa.Column("election_id", sa.String(length=32), nullable=False),
        sa.Column("source_authority", sa.String(length=128), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("identifier_type", sa.String(length=64), nullable=False),
        sa.Column("external_value_raw", sa.String(length=256), nullable=False),
        sa.Column("source_id", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["candidacy_id"], ["candidacy.candidacy_id"]),
        sa.ForeignKeyConstraint(["election_id"], ["election.election_id"]),
        sa.ForeignKeyConstraint(["source_id"], ["source_document.source_id"]),
        sa.PrimaryKeyConstraint("identifier_id"),
        sa.UniqueConstraint(
            "source_authority",
            "source_system",
            "identifier_type",
            "external_value_raw",
            "election_id",
            name="uq_csi_authority_system_type_value_election",
        ),
    )
    op.create_index(
        "ix_csi_lookup",
        "candidacy_source_identifier",
        [
            "source_authority",
            "source_system",
            "identifier_type",
            "external_value_raw",
            "election_id",
        ],
    )
    op.create_index(
        "ix_csi_candidacy_id",
        "candidacy_source_identifier",
        ["candidacy_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_csi_candidacy_id", table_name="candidacy_source_identifier")
    op.drop_index("ix_csi_lookup", table_name="candidacy_source_identifier")
    op.drop_table("candidacy_source_identifier")
