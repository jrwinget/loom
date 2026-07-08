"""Add app_settings key-value table

Revision ID: 013
Revises: 012
Create Date: 2026-06-19

backs runtime, admin-editable configuration that must change without a
restart — currently the AI engine config (key "ai"). the lite profile
materialises this table via create_all; the server profile via this
migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
