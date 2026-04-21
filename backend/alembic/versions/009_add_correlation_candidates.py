"""Add correlation_candidates and members

Stores multi-perspective correlation groupings: which assets appear
to cover the same event window, how confident the system is, and
which signals agreed vs disagreed. Per issue #40, this data layer
deliberately never auto-merges — candidates carry a status column
(pending/accepted/rejected) so a human resolves ambiguity.

Chains off 008 (clock drift fields, #39 merged 2026-04-21). The
confidence score leans on clock_confidence from 008 as one of the
fused signals.

Revision ID: 009
Revises: 008
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "correlation_candidates",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "case_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "start_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "end_utc",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "reasoning",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "decided_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_correlation_candidates_status",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_correlation_candidates_confidence_range",
        ),
        sa.CheckConstraint(
            "end_utc >= start_utc",
            name="ck_correlation_candidates_window_order",
        ),
    )
    op.create_index(
        "ix_correlation_candidates_case_status",
        "correlation_candidates",
        ["case_id", "status"],
    )
    op.create_index(
        "ix_correlation_candidates_case_window",
        "correlation_candidates",
        ["case_id", "start_utc", "end_utc"],
    )

    op.create_table(
        "correlation_candidate_members",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "candidate_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "correlation_candidates.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "candidate_id",
            "asset_id",
            name="uq_correlation_candidate_asset",
        ),
    )
    op.create_index(
        "ix_correlation_candidate_members_candidate",
        "correlation_candidate_members",
        ["candidate_id"],
    )
    op.create_index(
        "ix_correlation_candidate_members_asset",
        "correlation_candidate_members",
        ["asset_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_correlation_candidate_members_asset",
        table_name="correlation_candidate_members",
    )
    op.drop_index(
        "ix_correlation_candidate_members_candidate",
        table_name="correlation_candidate_members",
    )
    op.drop_table("correlation_candidate_members")

    op.drop_index(
        "ix_correlation_candidates_case_window",
        table_name="correlation_candidates",
    )
    op.drop_index(
        "ix_correlation_candidates_case_status",
        table_name="correlation_candidates",
    )
    op.drop_table("correlation_candidates")
