"""Add clock_offset_seconds and clock_confidence to assets

Records per-asset clock drift so reviewers can tell when device
clocks disagree on the same event. offset is in seconds (positive
= reported clock runs ahead of actual); confidence is a 0.0-1.0
score where 1.0 means all available time sources (EXIF, container,
filename) agree and 0.0 means strong disagreement. Both columns
are nullable — null means drift has not been detected or asserted.

This migration chains directly off 006 (the current head on the
``dev`` branch as of 2026-04-21). If another migration claims
revision "007" before this PR merges, rebase by renaming this
file to the next free number and updating ``down_revision`` to
point at that predecessor — see the existing 003 / 003b pair
for the house style on parallel-migration rebases.

Revision ID: 007
Revises: 006
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column(
            "clock_offset_seconds",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "clock_confidence",
            sa.Float(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("assets", "clock_confidence")
    op.drop_column("assets", "clock_offset_seconds")
