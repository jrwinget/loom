"""Add missing FK indexes on created_by columns

Revision ID: 003
Revises: 002
Create Date: 2026-03-30
"""

from alembic import op

revision: str = "003"
down_revision: str = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_plugins_created_by",
        "plugins",
        ["created_by"],
    )
    op.create_index(
        "ix_export_bundles_created_by",
        "export_bundles",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_export_bundles_created_by",
        table_name="export_bundles",
    )
    op.drop_index(
        "ix_plugins_created_by",
        table_name="plugins",
    )
