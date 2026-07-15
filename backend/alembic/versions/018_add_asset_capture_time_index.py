"""Add a (case_id, capture_time) index on assets

Revision ID: 018
Revises: 017
Create Date: 2026-07-09

clustering's compute_absolute_times opens by selecting a case's
assets with a non-null capture_time; on a large case that was a
scan. the timeline (case_id, event_time_start) index already
exists, so this adds only the genuinely-missing asset composite.

create_index does not rebuild the table, so this replays cleanly on
sqlite during the lite upgrade. the guards matter there: a lite db
built by create_all already carries the model's index, so a stale
stamp would otherwise crash the replay before uvicorn binds.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_assets_case_capture_time",
        "assets",
        ["case_id", "capture_time"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assets_case_capture_time",
        table_name="assets",
        if_exists=True,
    )
