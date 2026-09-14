"""Add narrative_drafts table

Revision ID: 023
Revises: 022
Create Date: 2026-09-14

backs the ai-drafted custody/audit narrative feature: a case's own
chain-of-custody/audit-log entries summarized as prose, gated behind a
human-review step before it can appear in any export. a dedicated table
rather than reusing ``annotations`` — see the model docstring — so
nothing in the export pipeline picks up a draft until deliberate,
filtered inclusion code is written for it.

the lite profile materialises this table via create_all; the server
profile via this migration (if_not_exists guards the replay case, same
pattern as migration 013).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narrative_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_entry_ids", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("model_params", sa.JSON(), nullable=True),
        sa.Column("generated_by", sa.Uuid(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["generated_by"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_narrative_drafts_case_id",
        "narrative_drafts",
        ["case_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_narrative_drafts_case_status",
        "narrative_drafts",
        ["case_id", "status"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_narrative_drafts_case_status",
        table_name="narrative_drafts",
        if_exists=True,
    )
    op.drop_index(
        "ix_narrative_drafts_case_id",
        table_name="narrative_drafts",
        if_exists=True,
    )
    op.drop_table("narrative_drafts", if_exists=True)
