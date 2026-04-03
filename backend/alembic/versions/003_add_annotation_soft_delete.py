"""Add soft delete columns to annotations

Revision ID: 003
Revises: 002
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "annotations",
        sa.Column(
            "deleted_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    op.add_column(
        "annotations",
        sa.Column(
            "deleted_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_annotations_case_deleted_at",
        "annotations",
        ["case_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_annotations_case_deleted_at",
        table_name="annotations",
    )
    op.drop_column("annotations", "deleted_by")
    op.drop_column("annotations", "deleted_at")
