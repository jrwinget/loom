"""tests for connection pool configuration and database indexes."""

from sqlalchemy import CheckConstraint
from sqlalchemy.ext.asyncio import create_async_engine

from loom.config import Settings
from loom.models import (
    Annotation,
    Asset,
    AuditLogEntry,
    Case,
    CaseMembership,
    ChainOfCustodyEntry,
    Derivative,
    DuplicateCluster,
    DuplicateClusterMember,
    ExportBundle,
    OcrRegion,
    Scene,
    TimelineEvent,
    TimelineEventEvidence,
    TranscriptSegment,
)
from loom.models.plugin import Plugin


class TestPoolConfiguration:
    """pool settings are wired into the engine."""

    def test_default_pool_settings(self) -> None:
        """settings expose pool defaults."""
        s = Settings(
            secret_key="x" * 32,
        )
        assert s.db_pool_size == 20
        assert s.db_max_overflow == 10
        assert s.db_pool_recycle == 3600
        assert s.db_pool_pre_ping is True
        assert s.db_pool_timeout == 30

    def test_pool_settings_override(self) -> None:
        """pool settings can be overridden."""
        s = Settings(
            secret_key="x" * 32,
            db_pool_size=5,
            db_max_overflow=2,
            db_pool_recycle=1800,
            db_pool_pre_ping=False,
            db_pool_timeout=10,
        )
        assert s.db_pool_size == 5
        assert s.db_max_overflow == 2
        assert s.db_pool_recycle == 1800
        assert s.db_pool_pre_ping is False
        assert s.db_pool_timeout == 10

    def test_engine_pool_size_applied(self) -> None:
        """create_async_engine receives pool_size."""
        s = Settings(
            secret_key="x" * 32,
            db_pool_size=7,
            db_max_overflow=3,
            db_pool_recycle=900,
            db_pool_timeout=15,
        )
        engine = create_async_engine(
            s.database_url,
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_recycle=s.db_pool_recycle,
            pool_pre_ping=s.db_pool_pre_ping,
            pool_timeout=s.db_pool_timeout,
        )
        pool = engine.pool
        assert pool.size() == 7
        assert pool._max_overflow == 3
        assert pool._recycle == 900
        assert pool._timeout == 15
        engine.sync_engine.dispose()


def _index_names(model: type) -> set[str]:
    """collect index names from a model's table."""
    return {idx.name for idx in model.__table__.indexes}


def _fk_ondelete(model: type, col_name: str) -> str | None:
    """return the ondelete rule for a foreign key column."""
    col = model.__table__.columns[col_name]
    for fk in col.foreign_keys:
        return fk.ondelete
    return None


def _check_constraint_names(model: type) -> set[str]:
    """collect check constraint names from a model's table."""
    return {
        c.name
        for c in model.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name
    }


class TestCompositeIndexes:
    """composite indexes exist on key query paths."""

    def test_annotation_case_asset_index(self) -> None:
        names = _index_names(Annotation)
        assert "ix_annotations_case_asset" in names

    def test_annotation_case_type_index(self) -> None:
        names = _index_names(Annotation)
        assert "ix_annotations_case_type" in names

    def test_timeline_event_case_status_index(self) -> None:
        names = _index_names(TimelineEvent)
        assert "ix_timeline_events_case_status" in names

    def test_timeline_event_case_time_index(self) -> None:
        names = _index_names(TimelineEvent)
        assert "ix_timeline_events_case_time" in names

    def test_transcript_segment_asset_start_index(self) -> None:
        names = _index_names(TranscriptSegment)
        assert "ix_transcript_segments_asset_start" in names

    def test_audit_log_created_actor_index(self) -> None:
        names = _index_names(AuditLogEntry)
        assert "ix_audit_log_created_actor" in names

    def test_audit_log_resource_type_index(self) -> None:
        names = _index_names(AuditLogEntry)
        assert "ix_audit_log_resource_type" in names

    def test_custody_asset_recorded_index(self) -> None:
        names = _index_names(ChainOfCustodyEntry)
        assert "ix_custody_asset_recorded" in names

    def test_asset_case_upload_status_index(self) -> None:
        names = _index_names(Asset)
        assert "ix_assets_case_upload_status" in names


class TestOnDeleteBehavior:
    """foreign keys have correct ON DELETE rules."""

    def test_asset_case_cascade(self) -> None:
        assert _fk_ondelete(Asset, "case_id") == "CASCADE"

    def test_annotation_case_cascade(self) -> None:
        assert _fk_ondelete(Annotation, "case_id") == "CASCADE"

    def test_annotation_asset_set_null(self) -> None:
        assert _fk_ondelete(Annotation, "asset_id") == "SET NULL"

    def test_timeline_event_case_cascade(self) -> None:
        assert _fk_ondelete(TimelineEvent, "case_id") == "CASCADE"

    def test_case_membership_case_cascade(self) -> None:
        assert _fk_ondelete(CaseMembership, "case_id") == "CASCADE"

    def test_case_membership_user_cascade(self) -> None:
        assert _fk_ondelete(CaseMembership, "user_id") == "CASCADE"

    def test_custody_asset_restrict(self) -> None:
        assert _fk_ondelete(ChainOfCustodyEntry, "asset_id") == "RESTRICT"

    def test_audit_actor_set_null(self) -> None:
        assert _fk_ondelete(AuditLogEntry, "actor_id") == "SET NULL"

    def test_transcript_asset_cascade(self) -> None:
        assert _fk_ondelete(TranscriptSegment, "asset_id") == "CASCADE"

    def test_ocr_asset_cascade(self) -> None:
        assert _fk_ondelete(OcrRegion, "asset_id") == "CASCADE"

    def test_scene_asset_cascade(self) -> None:
        assert _fk_ondelete(Scene, "asset_id") == "CASCADE"

    def test_derivative_asset_cascade(self) -> None:
        assert _fk_ondelete(Derivative, "asset_id") == "CASCADE"

    def test_export_bundle_case_cascade(self) -> None:
        assert _fk_ondelete(ExportBundle, "case_id") == "CASCADE"

    def test_duplicate_cluster_case_cascade(self) -> None:
        assert _fk_ondelete(DuplicateCluster, "case_id") == "CASCADE"

    def test_duplicate_member_cluster_cascade(self) -> None:
        assert _fk_ondelete(DuplicateClusterMember, "cluster_id") == "CASCADE"

    def test_duplicate_member_asset_cascade(self) -> None:
        assert _fk_ondelete(DuplicateClusterMember, "asset_id") == "CASCADE"

    def test_event_evidence_event_cascade(self) -> None:
        assert _fk_ondelete(TimelineEventEvidence, "event_id") == "CASCADE"

    def test_event_evidence_asset_set_null(self) -> None:
        assert _fk_ondelete(TimelineEventEvidence, "asset_id") == "SET NULL"


class TestCheckConstraints:
    """check constraints on status fields."""

    def test_case_status_check(self) -> None:
        names = _check_constraint_names(Case)
        assert "ck_cases_status" in names

    def test_asset_upload_status_check(self) -> None:
        names = _check_constraint_names(Asset)
        assert "ck_assets_upload_status" in names

    def test_asset_processing_status_check(self) -> None:
        names = _check_constraint_names(Asset)
        assert "ck_assets_processing_status" in names

    def test_timeline_event_status_check(self) -> None:
        names = _check_constraint_names(TimelineEvent)
        assert "ck_timeline_events_status" in names


class TestFkIndexes:
    """foreign key columns have indexes for join performance."""

    def test_plugin_created_by_has_index(self) -> None:
        """plugin.created_by column should have an index."""
        col = Plugin.__table__.c.created_by
        assert col.index is True or any(
            "created_by" in [c.name for c in idx.columns]
            for idx in Plugin.__table__.indexes
        )

    def test_export_bundle_created_by_has_index(self) -> None:
        """export_bundle.created_by column should have an index."""
        col = ExportBundle.__table__.c.created_by
        assert col.index is True or any(
            "created_by" in [c.name for c in idx.columns]
            for idx in ExportBundle.__table__.indexes
        )
