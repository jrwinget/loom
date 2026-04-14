"""Tests that model FK ondelete values match expectations."""

from loom.models.conflict import ConflictResolution
from loom.models.event_cluster import (
    EventCluster,
    EventClusterItem,
)
from loom.models.provenance import ProvenanceRecord
from loom.models.redaction import Redaction
from loom.models.revoked_token import RevokedToken


def _get_fk_ondelete(model: type, column_name: str) -> str | None:
    """extract ondelete from a model column's FK constraint."""
    table = model.__table__
    col = table.c[column_name]
    for fk in col.foreign_keys:
        return fk.ondelete
    return None


class TestEventClusterFKs:
    def test_case_id_cascade(self) -> None:
        assert _get_fk_ondelete(EventCluster, "case_id") == "CASCADE"

    def test_event_id_set_null(self) -> None:
        assert _get_fk_ondelete(EventCluster, "event_id") == "SET NULL"

    def test_reviewed_by_set_null(self) -> None:
        assert _get_fk_ondelete(EventCluster, "reviewed_by") == "SET NULL"


class TestEventClusterItemFKs:
    def test_cluster_id_cascade(self) -> None:
        assert _get_fk_ondelete(EventClusterItem, "cluster_id") == "CASCADE"

    def test_asset_id_cascade(self) -> None:
        assert _get_fk_ondelete(EventClusterItem, "asset_id") == "CASCADE"


class TestConflictResolutionFKs:
    def test_event_id_cascade(self) -> None:
        assert _get_fk_ondelete(ConflictResolution, "event_id") == "CASCADE"

    def test_resolved_by_restrict(self) -> None:
        assert _get_fk_ondelete(ConflictResolution, "resolved_by") == "RESTRICT"


class TestProvenanceRecordFKs:
    def test_asset_id_cascade(self) -> None:
        assert _get_fk_ondelete(ProvenanceRecord, "asset_id") == "CASCADE"

    def test_export_id_cascade(self) -> None:
        assert _get_fk_ondelete(ProvenanceRecord, "export_id") == "CASCADE"


class TestRedactionFKs:
    def test_asset_id_cascade(self) -> None:
        assert _get_fk_ondelete(Redaction, "asset_id") == "CASCADE"


class TestRevokedTokenFKs:
    def test_user_id_has_fk(self) -> None:
        table = RevokedToken.__table__
        col = table.c["user_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert str(fks[0].column) == "users.id"
