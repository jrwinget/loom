"""Add assets.processing_error

Revision ID: 014
Revises: 013
Create Date: 2026-07-08

persists the user-facing reason a processing run failed. the lite
in-process status map resets on restart, so without this column a
failed ingest shows as a bare "failed" after relaunch. the lite
profile materialises the column via create_all; the server profile
via this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a lite db built by create_all already carries this column, and
    # sqlite has no ADD COLUMN IF NOT EXISTS — inspect instead so a
    # stale stamp (012 installs) replays as a no-op
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("assets")}
    if "processing_error" in columns:
        return
    op.add_column(
        "assets",
        sa.Column("processing_error", sa.String(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {c["name"] for c in sa.inspect(bind).get_columns("assets")}
    if "processing_error" not in columns:
        return
    op.drop_column("assets", "processing_error")
