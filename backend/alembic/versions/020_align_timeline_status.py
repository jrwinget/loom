"""Align the timeline_events status constraint with the model

Revision ID: 020
Revises: 019
Create Date: 2026-07-24

the model check constraint allows draft/confirmed/disputed while the
001 postgres constraint also allowed 'archived'. no api or service
path could ever write a value outside the model set (sqlite enforces
the model constraint via create_all, postgres 500'd on PATCH), but
bundle import wrote unvalidated statuses until the same change that
ships this migration, so out-of-vocabulary rows may exist on either
engine. coerce those to draft first, then swap the postgres
constraint to the model's three-value form.

replay-safe: the update touches only out-of-vocabulary rows, and the
constraint swap drops IF EXISTS before re-adding. sqlite gets only
the data fix — its schema comes from create_all, which already
carries the model constraint, and a check-constraint swap there
would need a table rebuild for no behavioral change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # coerce before the constraint swap so ADD CONSTRAINT cannot fail
    # on a pre-existing 'archived' (or imported) row
    op.execute(
        "UPDATE timeline_events SET status = 'draft' "
        "WHERE status NOT IN ('draft', 'confirmed', 'disputed')"
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE timeline_events "
        "DROP CONSTRAINT IF EXISTS ck_timeline_events_status"
    )
    op.create_check_constraint(
        "ck_timeline_events_status",
        "timeline_events",
        "status IN ('draft', 'confirmed', 'disputed')",
    )


def downgrade() -> None:
    # the coercion is a one-way data fix; only the constraint shape
    # is restored
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE timeline_events "
        "DROP CONSTRAINT IF EXISTS ck_timeline_events_status"
    )
    op.create_check_constraint(
        "ck_timeline_events_status",
        "timeline_events",
        "status IN ('draft', 'confirmed', 'disputed', 'archived')",
    )
