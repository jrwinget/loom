"""Add export options, verification recency, and case hold columns

Revision ID: 019
Revises: 018
Create Date: 2026-07-24

three additive column groups that land together to keep the
migration chain short for parallel work:

- export_bundles.options preserves the export request as submitted;
  the manifest column is an output slot the builders overwrite, so
  requested options were unrecoverable after completion.
- assets.last_verified_at / last_verification_ok record when the
  stored bytes last re-hashed clean, so "when was this last proven
  intact?" stops requiring a scan of custody detail blobs.
- cases.hold_* implement litigation hold: while active, purge and
  asset deletion are refused (FRCP 37(e) preservation).

the lite profile materialises these via create_all; every add is
guarded by a column inspection so a stale stamp replays as a no-op
(the 014 pattern).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> tuple[tuple[str, sa.Column], ...]:
    # built fresh per call: a Column object binds to a Table on first
    # use, so a shared module-level instance would break a second
    # upgrade run inside the same process
    return (
        (
            "export_bundles",
            sa.Column("options", sa.JSON(), nullable=True),
        ),
        (
            "assets",
            sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        ),
        (
            "assets",
            sa.Column("last_verification_ok", sa.Boolean(), nullable=True),
        ),
        (
            "cases",
            sa.Column(
                "hold_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        ),
        (
            "cases",
            sa.Column("hold_reason", sa.String(), nullable=True),
        ),
        (
            "cases",
            sa.Column(
                "hold_set_by",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        ),
        (
            "cases",
            sa.Column("hold_set_at", sa.DateTime(), nullable=True),
        ),
    )


def _existing(columns: tuple[tuple[str, sa.Column], ...]) -> dict[str, set]:
    bind = op.get_bind()
    return {
        table: {c["name"] for c in sa.inspect(bind).get_columns(table)}
        for table in {t for t, _ in columns}
    }


def upgrade() -> None:
    columns = _columns()
    existing = _existing(columns)
    for table, column in columns:
        if column.name in existing[table]:
            continue
        op.add_column(table, column)


def downgrade() -> None:
    columns = _columns()
    existing = _existing(columns)
    for table, column in reversed(columns):
        if column.name not in existing[table]:
            continue
        op.drop_column(table, column.name)
