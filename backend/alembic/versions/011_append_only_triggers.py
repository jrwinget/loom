"""Enforce append-only semantics on audit + custody tables

Installs Postgres triggers that reject UPDATE and DELETE on
``audit_log`` and ``chain_of_custody_entries``. SQLite (Desktop
Lite) relies on ORM event listeners in
``loom.models._append_only`` for the same guarantee since
portable SQL triggers are awkward across engines.

Revision ID: 011
Revises: 010
Create Date: 2026-04-23

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = ("audit_log", "chain_of_custody_entries")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # sqlite (lite profile) relies on ORM-level enforcement.
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION loom_prevent_append_only_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                '% is append-only: % is not permitted',
                TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in _TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_update
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION loom_prevent_append_only_mutation();
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_delete
            BEFORE DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION loom_prevent_append_only_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")

    op.execute(
        "DROP FUNCTION IF EXISTS loom_prevent_append_only_mutation()"
    )
