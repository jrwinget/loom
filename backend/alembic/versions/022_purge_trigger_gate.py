"""Gate the append-only custody trigger for case purge

Revision ID: 022
Revises: 021
Create Date: 2026-07-24

migration 011's BEFORE DELETE trigger on chain_of_custody_entries
raises unconditionally, and postgres row triggers also fire for
FK-cascade deletes — so purging a case (cases → assets →
chain_of_custody_entries via ondelete=CASCADE) aborted on the
server profile while the lite profile (create_all installs no
triggers) purged fine.

the shared trigger function now permits DELETE on
chain_of_custody_entries only while the transaction-local
``loom.allow_purge`` setting is 'on' — SET LOCAL by the purge
service inside the same transaction that flushes the audit
tombstone, so the permission dies with the commit. the gate is
scoped to TG_TABLE_NAME and TG_OP so audit_log rows (including
the purge tombstone itself) and custody UPDATEs stay rejected
even inside a purge transaction.

replay-safe by construction: CREATE OR REPLACE swaps the function
body in place and the 011 triggers keep pointing at it.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
            IF TG_OP = 'DELETE'
                AND TG_TABLE_NAME = 'chain_of_custody_entries'
                AND current_setting('loom.allow_purge', true) = 'on'
            THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                '% is append-only: % is not permitted',
                TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # restore migration 011's unconditional function body verbatim.
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
