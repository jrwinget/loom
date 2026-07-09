"""Add cases.source_bundle_sha256 for import idempotency

Revision ID: 017
Revises: 016
Create Date: 2026-07-09

a case imported from a portable bundle records the bundle's sha256
so re-importing the same bundle is rejected (409) instead of
silently duplicating the whole case. the column is unique when set
and null for cases created directly.

batch_alter_table so the same revision runs on sqlite when the lite
upgrade path replays it; on postgres it renders as a plain ALTER.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a plain column add + a separate unique index: creating the index
    # does not rebuild the table, so this replays cleanly on sqlite
    # (a unique constraint inside batch_alter_table trips the sqlite
    # table-rebuild's circular-dependency sort).
    with op.batch_alter_table("cases") as batch:
        batch.add_column(
            sa.Column("source_bundle_sha256", sa.String(64), nullable=True)
        )
    op.create_index(
        "ix_cases_source_bundle_sha256",
        "cases",
        ["source_bundle_sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_cases_source_bundle_sha256", table_name="cases")
    with op.batch_alter_table("cases") as batch:
        batch.drop_column("source_bundle_sha256")
