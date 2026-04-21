"""Add clock_offset_seconds and clock_confidence to assets

Records per-asset clock drift so reviewers can tell when device
clocks disagree on the same event. offset is in seconds (positive
= reported clock runs ahead of actual); confidence is a 0.0-1.0
score where 1.0 means all available time sources (EXIF, container,
filename) agree and 0.0 means strong disagreement. Both columns
are nullable — null means drift has not been detected or asserted.

Chains off 007 (AI model metadata, #51 merged 2026-04-21).
Prior drafts of this PR pointed at 006; rebased to 007 after #51
landed on dev, matching the existing 003 / 003b house style for
sequential migrations landing in adjacent PRs.

Revision ID: 008
Revises: 007
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
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
