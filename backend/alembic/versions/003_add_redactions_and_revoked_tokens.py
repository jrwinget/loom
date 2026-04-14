"""Add redactions and revoked_tokens tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- redactions --
    op.create_table(
        "redactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("redacted_by", sa.Uuid(), nullable=False),
        sa.Column("redaction_type", sa.String(), nullable=False),
        sa.Column("regions", postgresql.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("output_storage_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["redacted_by"],
            ["users.id"],
        ),
        sa.CheckConstraint(
            "redaction_type IN ('blur', 'black_box', 'pixelate', 'audio_mute')",
            name="ck_redactions_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'complete', 'failed')",
            name="ck_redactions_status",
        ),
    )
    op.create_index(
        "ix_redactions_asset_id",
        "redactions",
        ["asset_id"],
    )

    # -- revoked_tokens --
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "revoked_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.UniqueConstraint("jti"),
    )
    op.create_index(
        "ix_revoked_tokens_jti",
        "revoked_tokens",
        ["jti"],
        unique=True,
    )
    op.create_index(
        "ix_revoked_tokens_user_id",
        "revoked_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_table("redactions")
