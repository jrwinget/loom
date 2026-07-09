"""Allow null audit_log.resource_id for collection-level routes

Revision ID: 016
Revises: 015
Create Date: 2026-07-08

the audit middleware only extracts a resource id when the request
path carries a UUID segment; collection-level routes (login, mfa,
case create, first-run) insert null. the NOT NULL constraint from
the initial schema made every one of those inserts fail, and the
middleware's catch-all reduced the failure to a warning — silently
dropping exactly the entries an audit trail exists for.

batch_alter_table so the same revision can run against sqlite when
the lite upgrade path lands (plain ALTER COLUMN is a table rebuild
there); on postgres it renders as a regular ALTER.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.alter_column(
            "resource_id",
            existing_type=sa.Uuid(),
            nullable=True,
        )


def downgrade() -> None:
    # fails if null rows exist by then — an append-only table cannot
    # be backfilled, and losing entries to satisfy a downgrade would
    # defeat the point of the trail
    with op.batch_alter_table("audit_log") as batch:
        batch.alter_column(
            "resource_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
