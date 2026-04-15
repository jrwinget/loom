"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-27

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- users (no FK deps) --
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("mfa_secret", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.CheckConstraint(
            "role IN ('admin', 'analyst', 'viewer')",
            name="ck_users_role",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # -- organizations --
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # -- organization_memberships --
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("org_id", "user_id"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member')",
            name="ck_org_memberships_role",
        ),
    )
    op.create_index(
        "ix_organization_memberships_org_id",
        "organization_memberships",
        ["org_id"],
    )
    op.create_index(
        "ix_organization_memberships_user_id",
        "organization_memberships",
        ["user_id"],
    )

    # -- cases --
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived', 'closed')",
            name="ck_cases_status",
        ),
    )

    # -- case_memberships --
    op.create_table(
        "case_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("case_id", "user_id"),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_case_memberships_role",
        ),
    )

    # -- assets --
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("media_type", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("sha512_hash", sa.String(128), nullable=False),
        sa.Column("upload_status", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("metadata_raw", postgresql.JSON(), nullable=True),
        sa.Column("metadata_extracted", postgresql.JSON(), nullable=True),
        sa.Column("capture_time", sa.DateTime(), nullable=True),
        sa.Column("capture_location_lat", sa.Float(), nullable=True),
        sa.Column("capture_location_lon", sa.Float(), nullable=True),
        sa.Column("processing_status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint(
            "upload_status IN ('pending', 'uploading', 'complete', 'failed')",
            name="ck_assets_upload_status",
        ),
        sa.CheckConstraint(
            "processing_status IN "
            "('pending', 'processing', 'complete', 'failed')",
            name="ck_assets_processing_status",
        ),
        sa.CheckConstraint(
            "media_type IN ('video', 'image', 'audio', 'document')",
            name="ck_assets_media_type",
        ),
    )
    op.create_index("ix_assets_case_id", "assets", ["case_id"])
    op.create_index("ix_assets_sha256_hash", "assets", ["sha256_hash"])

    # -- derivatives --
    op.create_table(
        "derivatives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256_hash", sa.String(64), nullable=False),
        sa.Column("generation_params", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_derivatives_asset_id", "derivatives", ["asset_id"])

    # -- annotations --
    op.create_table(
        "annotations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("time_start", sa.Float(), nullable=True),
        sa.Column("time_end", sa.Float(), nullable=True),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("spatial_region", postgresql.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "type IN ('observation', 'claim', 'dispute', "
            "'needs_verification', 'note')",
            name="ck_annotations_type",
        ),
    )
    op.create_index("ix_annotations_case_id", "annotations", ["case_id"])
    op.create_index("ix_annotations_asset_id", "annotations", ["asset_id"])
    op.create_index(
        "ix_annotations_case_id_asset_id",
        "annotations",
        ["case_id", "asset_id"],
    )

    # -- timeline_events --
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("event_time_start", sa.DateTime(), nullable=False),
        sa.Column("event_time_end", sa.DateTime(), nullable=True),
        sa.Column("time_precision", sa.String(), nullable=False),
        sa.Column("location_description", sa.String(), nullable=True),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lon", sa.Float(), nullable=True),
        sa.Column("location_confidence", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'disputed', 'archived')",
            name="ck_timeline_events_status",
        ),
    )
    op.create_index(
        "ix_timeline_events_case_id",
        "timeline_events",
        ["case_id"],
    )
    op.create_index(
        "ix_timeline_events_case_id_status",
        "timeline_events",
        ["case_id", "status"],
    )

    # -- timeline_event_evidence --
    op.create_table(
        "timeline_event_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("annotation_id", sa.Uuid(), nullable=True),
        sa.Column("derivative_id", sa.Uuid(), nullable=True),
        sa.Column("clip_start", sa.Float(), nullable=True),
        sa.Column("clip_end", sa.Float(), nullable=True),
        sa.Column("relationship", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("linked_by", sa.Uuid(), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["timeline_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["annotation_id"],
            ["annotations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["derivative_id"],
            ["derivatives.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_timeline_event_evidence_relationship",
        ),
    )
    op.create_index(
        "ix_timeline_event_evidence_event_id",
        "timeline_event_evidence",
        ["event_id"],
    )

    # -- chain_of_custody_entries (append-only) --
    op.create_table(
        "chain_of_custody_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("detail", postgresql.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_chain_of_custody_entries_asset_id",
        "chain_of_custody_entries",
        ["asset_id"],
    )
    op.create_index(
        "ix_chain_of_custody_entries_asset_id_timestamp",
        "chain_of_custody_entries",
        ["asset_id", "timestamp"],
    )

    # -- audit_log (append-only) --
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("detail", postgresql.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_audit_log_created_at_actor_id",
        "audit_log",
        ["timestamp", "actor_id"],
    )

    # -- export_bundles --
    op.create_table(
        "export_bundles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("sha256_hash", sa.String(64), nullable=True),
        sa.Column("manifest", postgresql.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'complete', 'failed')",
            name="ck_export_bundles_status",
        ),
    )
    op.create_index(
        "ix_export_bundles_case_id",
        "export_bundles",
        ["case_id"],
    )

    # -- transcript_segments --
    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("speaker_label", sa.String(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_transcript_segments_asset_id",
        "transcript_segments",
        ["asset_id"],
    )
    op.create_index(
        "ix_transcript_segments_asset_id_start_time",
        "transcript_segments",
        ["asset_id", "start_time"],
    )

    # -- ocr_regions --
    op.create_table(
        "ocr_regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.Float(), nullable=True),
        sa.Column("bounding_box", postgresql.JSON(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_ocr_regions_asset_id", "ocr_regions", ["asset_id"])

    # -- scenes --
    op.create_table(
        "scenes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("start_frame", sa.Integer(), nullable=False),
        sa.Column("end_frame", sa.Integer(), nullable=False),
        sa.Column("thumbnail_key", sa.String(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_scenes_asset_id", "scenes", ["asset_id"])

    # -- duplicate_clusters --
    op.create_table(
        "duplicate_clusters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'dismissed')",
            name="ck_duplicate_clusters_status",
        ),
    )
    op.create_index(
        "ix_duplicate_clusters_case_id",
        "duplicate_clusters",
        ["case_id"],
    )

    # -- duplicate_cluster_members --
    op.create_table(
        "duplicate_cluster_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("phash", sa.String(16), nullable=True),
        sa.Column("distance", sa.Float(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["duplicate_clusters.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "cluster_id", "asset_id", name="uq_cluster_asset"
        ),
    )
    op.create_index(
        "ix_duplicate_cluster_members_cluster_id",
        "duplicate_cluster_members",
        ["cluster_id"],
    )
    op.create_index(
        "ix_duplicate_cluster_members_asset_id",
        "duplicate_cluster_members",
        ["asset_id"],
    )

    # -- conflict_resolutions --
    op.create_table(
        "conflict_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("resolution_type", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["timeline_events.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_conflict_resolutions_event_id",
        "conflict_resolutions",
        ["event_id"],
    )

    # -- event_clusters --
    op.create_table(
        "event_clusters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("proposed_title", sa.String(), nullable=False),
        sa.Column("proposed_description", sa.Text(), nullable=True),
        sa.Column("time_window_start", sa.DateTime(), nullable=False),
        sa.Column("time_window_end", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["timeline_events.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'rejected', 'merged')",
            name="ck_event_clusters_status",
        ),
    )
    op.create_index(
        "ix_event_clusters_case_id",
        "event_clusters",
        ["case_id"],
    )

    # -- event_cluster_items --
    op.create_table(
        "event_cluster_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("content_id", sa.Uuid(), nullable=False),
        sa.Column(
            "absolute_time_start", sa.DateTime(), nullable=False
        ),
        sa.Column(
            "absolute_time_end", sa.DateTime(), nullable=True
        ),
        sa.Column("text_preview", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["event_clusters.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_event_cluster_items_cluster_id",
        "event_cluster_items",
        ["cluster_id"],
    )

    # -- provenance_records --
    op.create_table(
        "provenance_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("export_id", sa.Uuid(), nullable=True),
        sa.Column("manifest_data", postgresql.JSON(), nullable=False),
        sa.Column("manifest_url", sa.String(), nullable=True),
        sa.Column("claim_generator", sa.String(), nullable=False),
        sa.Column("actions", postgresql.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["export_id"],
            ["export_bundles.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_provenance_records_asset_id",
        "provenance_records",
        ["asset_id"],
    )
    op.create_index(
        "ix_provenance_records_export_id",
        "provenance_records",
        ["export_id"],
    )

    # -- shared_evidence_links --
    op.create_table(
        "shared_evidence_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_case_id", sa.Uuid(), nullable=False),
        sa.Column("target_case_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("shared_by", sa.Uuid(), nullable=False),
        sa.Column("access_level", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["source_case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_case_id"],
            ["cases.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shared_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "access_level IN ('view', 'annotate')",
            name="ck_shared_evidence_links_access_level",
        ),
    )
    op.create_index(
        "ix_shared_evidence_links_source_case_id",
        "shared_evidence_links",
        ["source_case_id"],
    )
    op.create_index(
        "ix_shared_evidence_links_target_case_id",
        "shared_evidence_links",
        ["target_case_id"],
    )
    op.create_index(
        "ix_shared_evidence_links_asset_id",
        "shared_evidence_links",
        ["asset_id"],
    )

    # -- plugins --
    op.create_table(
        "plugins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("plugin_type", sa.String(50), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("config", postgresql.JSON(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("name"),
    )

    # -- webhooks --
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plugin_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("events", postgresql.JSON(), nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("last_triggered_at", sa.DateTime(), nullable=True),
        sa.Column(
            "failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["plugin_id"],
            ["plugins.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_webhooks_plugin_id", "webhooks", ["plugin_id"])

    # -- webhook_deliveries --
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("webhook_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["webhooks.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_webhook_id",
        "webhook_deliveries",
        ["webhook_id"],
    )


def downgrade() -> None:
    # drop in reverse dependency order
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
    op.drop_table("plugins")
    op.drop_table("shared_evidence_links")
    op.drop_table("provenance_records")
    op.drop_table("event_cluster_items")
    op.drop_table("event_clusters")
    op.drop_table("conflict_resolutions")
    op.drop_table("duplicate_cluster_members")
    op.drop_table("duplicate_clusters")
    op.drop_table("scenes")
    op.drop_table("ocr_regions")
    op.drop_table("transcript_segments")
    op.drop_table("export_bundles")
    op.drop_table("audit_log")
    op.drop_table("chain_of_custody_entries")
    op.drop_table("timeline_event_evidence")
    op.drop_table("timeline_events")
    op.drop_table("annotations")
    op.drop_table("derivatives")
    op.drop_table("assets")
    op.drop_table("case_memberships")
    op.drop_table("cases")
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_table("users")
