"""Add AI model metadata columns to AI-produced artifacts

Adds model_name, model_version, model_params to
transcript_segments, ocr_regions, and scenes so every
AI-produced row carries provenance back to the model that
produced it. Existing rows are backfilled with 'unknown'
for model_name / model_version; model_params stays NULL
because we cannot reconstruct the parameters after the
fact.

Revision ID: 007
Revises: 006
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AI_TABLES: tuple[str, ...] = (
    "transcript_segments",
    "ocr_regions",
    "scenes",
)


def upgrade() -> None:
    for table in _AI_TABLES:
        op.add_column(
            table,
            sa.Column("model_name", sa.String(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("model_version", sa.String(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column(
                "model_params",
                postgresql.JSON(astext_type=sa.Text()),
                nullable=True,
            ),
        )
        # backfill existing rows per issue #43 spec
        op.execute(
            sa.text(
                f"UPDATE {table} "
                "SET model_name = 'unknown', "
                "model_version = 'unknown' "
                "WHERE model_name IS NULL"
            )
        )


def downgrade() -> None:
    for table in _AI_TABLES:
        op.drop_column(table, "model_params")
        op.drop_column(table, "model_version")
        op.drop_column(table, "model_name")
