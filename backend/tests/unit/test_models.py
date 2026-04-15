from uuid import UUID

from loom.models import (
    Annotation,
    Asset,
    AuditLogEntry,
    Case,
    CaseMembership,
    ChainOfCustodyEntry,
    Derivative,
    ExportBundle,
    TimelineEvent,
    TimelineEventEvidence,
    User,
)
from loom.models.base import Base, TimestampMixin, _generate_uuid7

ALL_MODELS = [
    User,
    Case,
    CaseMembership,
    Asset,
    Derivative,
    ChainOfCustodyEntry,
    Annotation,
    TimelineEvent,
    TimelineEventEvidence,
    ExportBundle,
    AuditLogEntry,
]


class TestUUIDMixin:
    def test_id_column_exists(self) -> None:
        """uuid mixin adds an id column to models."""
        for model in ALL_MODELS:
            table = model.__table__
            assert "id" in table.columns, f"{model.__name__} missing id column"

    def test_id_is_primary_key(self) -> None:
        """id column is the primary key."""
        for model in ALL_MODELS:
            col = model.__table__.columns["id"]
            assert col.primary_key, f"{model.__name__}.id is not a primary key"

    def test_uuid_default_generates_valid_uuid(self) -> None:
        """default factory produces a valid uuid."""
        value = _generate_uuid7()
        assert isinstance(value, UUID)


class TestTimestampMixin:
    def test_created_at_exists_on_timestamp_models(self) -> None:
        """models using timestamp mixin have created_at."""
        timestamp_models = [
            m for m in ALL_MODELS if issubclass(m, TimestampMixin)
        ]
        assert len(timestamp_models) > 0
        for model in timestamp_models:
            assert "created_at" in model.__table__.columns

    def test_updated_at_exists_on_timestamp_models(self) -> None:
        """models using timestamp mixin have updated_at."""
        timestamp_models = [
            m for m in ALL_MODELS if issubclass(m, TimestampMixin)
        ]
        for model in timestamp_models:
            assert "updated_at" in model.__table__.columns

    def test_append_only_tables_lack_updated_at(self) -> None:
        """append-only tables should not have updated_at."""
        append_only = [
            ChainOfCustodyEntry,
            AuditLogEntry,
            Derivative,
            ExportBundle,
        ]
        for model in append_only:
            assert not issubclass(model, TimestampMixin), (
                f"{model.__name__} should not use TimestampMixin"
            )


class TestBaseDeclarative:
    def test_base_is_declarative(self) -> None:
        """base inherits from declarative base."""
        assert hasattr(Base, "metadata")
        assert hasattr(Base, "registry")


class TestUserModel:
    def test_table_name(self) -> None:
        assert User.__tablename__ == "users"

    def test_columns(self) -> None:
        cols = {c.name for c in User.__table__.columns}
        expected = {
            "id",
            "email",
            "display_name",
            "role",
            "password_hash",
            "mfa_secret",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_email_is_unique(self) -> None:
        col = User.__table__.columns["email"]
        assert col.unique


class TestCaseModel:
    def test_table_name(self) -> None:
        assert Case.__tablename__ == "cases"

    def test_columns(self) -> None:
        cols = {c.name for c in Case.__table__.columns}
        expected = {
            "id",
            "name",
            "description",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)


class TestCaseMembershipModel:
    def test_table_name(self) -> None:
        assert CaseMembership.__tablename__ == "case_memberships"

    def test_unique_constraint(self) -> None:
        constraints = [
            c
            for c in CaseMembership.__table__.constraints
            if hasattr(c, "columns")
            and {col.name for col in c.columns} == {"case_id", "user_id"}
        ]
        assert len(constraints) > 0


class TestAssetModel:
    def test_table_name(self) -> None:
        assert Asset.__tablename__ == "assets"

    def test_columns(self) -> None:
        cols = {c.name for c in Asset.__table__.columns}
        expected = {
            "id",
            "case_id",
            "original_filename",
            "storage_key",
            "media_type",
            "mime_type",
            "file_size_bytes",
            "sha256_hash",
            "sha512_hash",
            "upload_status",
            "uploaded_by",
            "uploaded_at",
            "metadata_raw",
            "metadata_extracted",
            "capture_time",
            "capture_location_lat",
            "capture_location_lon",
            "processing_status",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_storage_key_unique(self) -> None:
        col = Asset.__table__.columns["storage_key"]
        assert col.unique


class TestDerivativeModel:
    def test_table_name(self) -> None:
        assert Derivative.__tablename__ == "derivatives"

    def test_has_created_at_but_no_updated_at(self) -> None:
        cols = {c.name for c in Derivative.__table__.columns}
        assert "created_at" in cols
        assert "updated_at" not in cols


class TestChainOfCustodyModel:
    def test_table_name(self) -> None:
        assert ChainOfCustodyEntry.__tablename__ == "chain_of_custody_entries"

    def test_no_updated_at(self) -> None:
        cols = {c.name for c in ChainOfCustodyEntry.__table__.columns}
        assert "updated_at" not in cols


class TestAnnotationModel:
    def test_table_name(self) -> None:
        assert Annotation.__tablename__ == "annotations"

    def test_columns(self) -> None:
        cols = {c.name for c in Annotation.__table__.columns}
        expected = {
            "id",
            "case_id",
            "asset_id",
            "type",
            "content",
            "time_start",
            "time_end",
            "frame_number",
            "spatial_region",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)


class TestTimelineEventModel:
    def test_table_name(self) -> None:
        assert TimelineEvent.__tablename__ == "timeline_events"


class TestTimelineEventEvidenceModel:
    def test_table_name(self) -> None:
        assert TimelineEventEvidence.__tablename__ == "timeline_event_evidence"


class TestExportBundleModel:
    def test_table_name(self) -> None:
        assert ExportBundle.__tablename__ == "export_bundles"

    def test_has_created_at_but_no_updated_at(self) -> None:
        cols = {c.name for c in ExportBundle.__table__.columns}
        assert "created_at" in cols
        assert "updated_at" not in cols


class TestAuditLogModel:
    def test_table_name(self) -> None:
        assert AuditLogEntry.__tablename__ == "audit_log"

    def test_no_updated_at(self) -> None:
        cols = {c.name for c in AuditLogEntry.__table__.columns}
        assert "updated_at" not in cols


class TestEnumStrings:
    """verify enum-like columns use plain strings."""

    def test_user_role_values(self) -> None:
        col = User.__table__.columns["role"]
        assert str(col.type) == "VARCHAR", (
            "role should be a string column, not a db enum"
        )

    def test_case_status_values(self) -> None:
        col = Case.__table__.columns["status"]
        assert str(col.type) == "VARCHAR"

    def test_asset_media_type_values(self) -> None:
        col = Asset.__table__.columns["media_type"]
        assert str(col.type) == "VARCHAR"

    def test_derivative_type_values(self) -> None:
        col = Derivative.__table__.columns["type"]
        assert str(col.type) == "VARCHAR"
