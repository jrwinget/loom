"""Align the migrated schema with the model metadata

Revision ID: 015
Revises: 014
Create Date: 2026-07-08

the lite profile materialises its schema from the models
(create_all) while the server runs migrations; the two had drifted
apart since the early revisions. this migration brings the server
side up to the models where the models are the intent (index names
and coverage, users.email uniqueness shape, redundant constraints,
timestamp flavor); the reverse direction — fk ondelete behavior the
migrations had but the models lacked — was fixed in the models in
the same change. test_schema_parity.py keeps the two in lockstep
from here on.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, old name, new name) — models are the naming truth
_RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "annotations",
        "ix_annotations_case_id_asset_id",
        "ix_annotations_case_asset",
    ),
    (
        "audit_log",
        "ix_audit_log_created_at_actor_id",
        "ix_audit_log_created_actor",
    ),
    (
        "chain_of_custody_entries",
        "ix_chain_of_custody_entries_asset_id_timestamp",
        "ix_custody_asset_recorded",
    ),
    (
        "correlation_candidate_members",
        "ix_correlation_candidate_members_asset",
        "ix_correlation_candidate_members_asset_id",
    ),
    (
        "correlation_candidate_members",
        "ix_correlation_candidate_members_candidate",
        "ix_correlation_candidate_members_candidate_id",
    ),
    (
        "timeline_events",
        "ix_timeline_events_case_id_status",
        "ix_timeline_events_case_status",
    ),
    (
        "transcript_segments",
        "ix_transcript_segments_asset_id_start_time",
        "ix_transcript_segments_asset_start",
    ),
)

# indexes the models declared that no migration ever created
_MISSING_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_annotations_case_type", "annotations", ("case_id", "type")),
    (
        "ix_assets_case_upload_status",
        "assets",
        ("case_id", "upload_status"),
    ),
    ("ix_audit_log_resource_type", "audit_log", ("resource_type",)),
    (
        "ix_correlation_candidates_case_id",
        "correlation_candidates",
        ("case_id",),
    ),
    (
        "ix_timeline_events_case_time",
        "timeline_events",
        ("case_id", "event_time_start"),
    ),
)


def upgrade() -> None:
    for _table, old, new in _RENAMES:
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")

    for name, table, cols in _MISSING_INDEXES:
        op.create_index(name, table, list(cols))

    # models declare email as a unique index; the migration-era shape
    # was a redundant unique constraint plus a non-unique index
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # jti already has a unique index (ix_revoked_tokens_jti); the
    # extra unique constraint was redundant
    op.drop_constraint(
        "revoked_tokens_jti_key", "revoked_tokens", type_="unique"
    )
    # server_default=now() exists, so enforcing the model's NOT NULL
    # is safe
    op.alter_column(
        "revoked_tokens",
        "revoked_at",
        existing_type=sa.TIMESTAMP(),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )

    # every other table stores naive utc; the correlation migration
    # alone used timestamptz. values are utc either way.
    for col in ("created_at", "updated_at"):
        op.alter_column(
            "correlation_candidates",
            col,
            existing_type=sa.TIMESTAMP(timezone=True),
            type_=sa.TIMESTAMP(),
            existing_nullable=False,
            existing_server_default=sa.text("now()"),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for col in ("created_at", "updated_at"):
        op.alter_column(
            "correlation_candidates",
            col,
            existing_type=sa.TIMESTAMP(),
            type_=sa.TIMESTAMP(timezone=True),
            existing_nullable=False,
            existing_server_default=sa.text("now()"),
            postgresql_using=f"{col} AT TIME ZONE 'UTC'",
        )

    op.alter_column(
        "revoked_tokens",
        "revoked_at",
        existing_type=sa.TIMESTAMP(),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.create_unique_constraint(
        "revoked_tokens_jti_key", "revoked_tokens", ["jti"]
    )

    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"])
    op.create_unique_constraint("users_email_key", "users", ["email"])

    for name, table, _cols in _MISSING_INDEXES:
        op.drop_index(name, table_name=table)

    for _table, old, new in _RENAMES:
        op.execute(f"ALTER INDEX {new} RENAME TO {old}")
