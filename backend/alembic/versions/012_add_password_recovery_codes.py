"""Add password_recovery_codes column to users

Revision ID: 012
Revises: 011
Create Date: 2026-05-13

separate from MFA's existing `recovery_codes` column. those codes
are scoped to the second-factor challenge; these are scoped to the
"i forgot my password" flow. keeping them in distinct columns keeps
each surface single-purpose and lets an admin disable one without
touching the other.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_recovery_codes",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_recovery_codes")
