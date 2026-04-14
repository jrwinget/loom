"""Add soft delete columns to assets

Revision ID: 002
Revises: 001
Create Date: 2026-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "deleted_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "deleted_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_assets_case_deleted_at",
        "assets",
        ["case_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assets_case_deleted_at",
        table_name="assets",
    )
    op.drop_column("assets", "deleted_by")
    op.drop_column("assets", "deleted_at")
