"""Change chain_of_custody asset_id FK from RESTRICT to CASCADE

Revision ID: 004
Revises: 003
Create Date: 2026-03-31
"""

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "chain_of_custody_entries_asset_id_fkey",
        "chain_of_custody_entries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "chain_of_custody_entries_asset_id_fkey",
        "chain_of_custody_entries",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chain_of_custody_entries_asset_id_fkey",
        "chain_of_custody_entries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "chain_of_custody_entries_asset_id_fkey",
        "chain_of_custody_entries",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )
