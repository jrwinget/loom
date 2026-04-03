from datetime import UTC, datetime
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)
from uuid import UUID

import pytest

from loom.models.provenance import ProvenanceRecord
from loom.services.provenance import (
    CLAIM_GENERATOR,
    build_c2pa_manifest,
    create_provenance_record,
    sign_manifest,
)

_ASSET_ID = UUID("01912345-6789-7abc-8def-012345678902")
_CASE_ID = UUID("01912345-6789-7abc-8def-0123456789ef")
_NOW = datetime(2025, 1, 1, tzinfo=UTC)


def _mock_asset() -> MagicMock:
    """build a mock asset for testing."""
    asset = MagicMock()
    asset.id = _ASSET_ID
    asset.case_id = _CASE_ID
    asset.original_filename = "test.jpg"
    asset.mime_type = "image/jpeg"
    asset.sha256_hash = "a" * 64
    return asset


def _mock_custody_entry(
    action: str = "uploaded",
) -> MagicMock:
    """build a mock chain of custody entry."""
    entry = MagicMock()
    entry.asset_id = _ASSET_ID
    entry.action = action
    entry.timestamp = _NOW
    return entry


async def test_build_c2pa_manifest_creates_valid_structure() -> None:
    """build_c2pa_manifest returns manifest with hash and custody."""
    asset = _mock_asset()
    custody = _mock_custody_entry("uploaded")

    # mock session
    session = AsyncMock()

    # first execute: asset query
    asset_result = MagicMock()
    asset_result.scalar_one_or_none.return_value = asset

    # second execute: custody query
    custody_scalars = MagicMock()
    custody_scalars.all.return_value = [custody]
    custody_result = MagicMock()
    custody_result.scalars.return_value = custody_scalars

    session.execute = AsyncMock(side_effect=[asset_result, custody_result])

    manifest = await build_c2pa_manifest(
        str(_ASSET_ID),
        [{"action": "c2pa.exported"}],
        session,
    )

    assert manifest["claim_generator"] == CLAIM_GENERATOR
    assert manifest["title"] == "test.jpg"
    assert manifest["format"] == "image/jpeg"
    assert manifest["instance_id"] == str(_ASSET_ID)

    # check assertions
    assertions = manifest["assertions"]
    assert len(assertions) == 2

    # hash assertion
    hash_assertion = assertions[0]
    assert hash_assertion["label"] == "c2pa.hash.data"
    assert hash_assertion["data"]["hash"] == "a" * 64

    # actions assertion includes custody chain + passed actions
    actions_assertion = assertions[1]
    actions_list = actions_assertion["data"]["actions"]
    assert len(actions_list) == 2
    assert actions_list[0]["action"] == "uploaded"
    assert actions_list[1]["action"] == "c2pa.exported"


async def test_build_c2pa_manifest_raises_for_missing_asset() -> None:
    """build_c2pa_manifest raises ValueError for unknown asset."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)

    with pytest.raises(ValueError, match="not found"):
        await build_c2pa_manifest(str(_ASSET_ID), [], session)


def test_sign_manifest_handles_missing_c2pa() -> None:
    """sign_manifest returns None when c2pa is not installed."""
    manifest = {
        "claim_generator": CLAIM_GENERATOR,
        "format": "image/jpeg",
    }

    with patch(
        "loom.services.provenance._c2pa_available",
        return_value=False,
    ):
        result = sign_manifest(manifest, "/tmp/in.jpg", "/tmp/out.jpg")  # noqa: S108

    assert result is None


def test_sign_manifest_handles_unsupported_format() -> None:
    """sign_manifest returns None for unsupported file formats."""
    manifest = {
        "claim_generator": CLAIM_GENERATOR,
        "format": "application/pdf",
    }

    with patch(
        "loom.services.provenance._c2pa_available",
        return_value=True,
    ):
        result = sign_manifest(
            manifest,
            "/tmp/in.pdf",  # noqa: S108
            "/tmp/out.pdf",  # noqa: S108
        )

    assert result is None


async def test_create_provenance_record_stores_correctly() -> None:
    """create_provenance_record persists record with correct fields."""
    session = AsyncMock()
    session.add = MagicMock()
    manifest = {"claim_generator": CLAIM_GENERATOR}
    actions = [{"action": "uploaded"}]

    await create_provenance_record(
        session,
        str(_ASSET_ID),
        None,
        manifest,
        actions,
    )

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()

    added_obj = session.add.call_args[0][0]
    assert isinstance(added_obj, ProvenanceRecord)
    assert added_obj.asset_id == _ASSET_ID
    assert added_obj.export_id is None
    assert added_obj.manifest_data == manifest
    assert added_obj.claim_generator == CLAIM_GENERATOR
    assert added_obj.actions == actions


def test_provenance_record_model_validation() -> None:
    """ProvenanceRecord model can be instantiated correctly."""
    record = ProvenanceRecord(
        asset_id=_ASSET_ID,
        export_id=None,
        manifest_data={"test": True},
        manifest_url=None,
        claim_generator=CLAIM_GENERATOR,
        actions=[{"action": "test"}],
    )

    assert record.asset_id == _ASSET_ID
    assert record.export_id is None
    assert record.manifest_data == {"test": True}
    assert record.claim_generator == CLAIM_GENERATOR
    assert record.actions == [{"action": "test"}]


class TestGetAssetProvenance:
    """get_asset_provenance with case_id verification."""

    async def test_returns_records_for_valid_asset(self) -> None:
        """returns provenance records when asset belongs to case."""
        from loom.services.provenance import get_asset_provenance

        asset = _mock_asset()
        record = MagicMock(spec=ProvenanceRecord)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # asset verification query
                m.scalar_one_or_none.return_value = asset
            else:
                # provenance records query
                m.scalars.return_value.all.return_value = [record]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        records = await get_asset_provenance(
            session, str(_ASSET_ID), str(_CASE_ID)
        )
        assert len(records) == 1

    async def test_returns_empty_for_wrong_case(self) -> None:
        """returns empty list when asset not in case (idor)."""
        from loom.services.provenance import get_asset_provenance

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        records = await get_asset_provenance(
            session,
            str(_ASSET_ID),
            "99999999-9999-9999-9999-999999999999",
        )
        assert records == []


class TestGetExportProvenance:
    """get_export_provenance with case_id verification."""

    async def test_returns_records_for_valid_export(self) -> None:
        """returns provenance records when export belongs to case."""
        from loom.services.provenance import get_export_provenance

        export = MagicMock()
        record = MagicMock(spec=ProvenanceRecord)

        session = AsyncMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                m.scalar_one_or_none.return_value = export
            else:
                m.scalars.return_value.all.return_value = [record]
            return m

        session.execute = AsyncMock(side_effect=mock_execute)

        export_id = "01912345-6789-7abc-8def-0123456789ab"
        records = await get_export_provenance(session, export_id, str(_CASE_ID))
        assert len(records) == 1

    async def test_returns_empty_for_wrong_case(self) -> None:
        """returns empty when export not in case."""
        from loom.services.provenance import get_export_provenance

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        records = await get_export_provenance(
            session,
            "01912345-6789-7abc-8def-0123456789ab",
            "99999999-9999-9999-9999-999999999999",
        )
        assert records == []


class TestEmbedProvenanceInExport:
    """embed_provenance_in_export orchestration."""

    async def test_returns_false_without_c2pa(self) -> None:
        """returns False when c2pa not installed."""
        from loom.services.provenance import embed_provenance_in_export

        session = AsyncMock()
        storage = MagicMock()

        with patch(
            "loom.services.provenance._c2pa_available",
            return_value=False,
        ):
            result = await embed_provenance_in_export(
                session, "export-id", str(_CASE_ID), storage
            )
        assert result is False

    async def test_returns_false_for_wrong_case(self) -> None:
        """returns False when export not in case."""
        from loom.services.provenance import embed_provenance_in_export

        session = AsyncMock()
        storage = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        with patch(
            "loom.services.provenance._c2pa_available",
            return_value=True,
        ):
            result = await embed_provenance_in_export(
                session,
                "01912345-6789-7abc-8def-0123456789ab",
                "99999999-9999-9999-9999-999999999999",
                storage,
            )
        assert result is False

    async def test_records_provenance_for_unsupported_format(
        self,
    ) -> None:
        """records provenance even for unsupported mime types."""
        from loom.services.provenance import embed_provenance_in_export

        export = MagicMock()
        export.id = "export-1"
        export.case_id = _CASE_ID

        asset = MagicMock()
        asset.id = _ASSET_ID
        asset.original_filename = "doc.pdf"
        asset.mime_type = "application/pdf"
        asset.sha256_hash = "b" * 64

        session = AsyncMock()
        session.add = MagicMock()
        call_count = 0

        async def mock_execute(query: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            if call_count == 1:
                # export verification
                m.scalar_one_or_none.return_value = export
            elif call_count == 2:
                # assets query
                m.scalars.return_value.all.return_value = [asset]
            elif call_count == 3:
                # asset query in build_c2pa_manifest
                m.scalar_one_or_none.return_value = asset
            elif call_count == 4:
                # custody entries
                m.scalars.return_value.all.return_value = []
            else:
                m.scalar_one_or_none.return_value = None
                m.scalars.return_value.all.return_value = []
            return m

        session.execute = AsyncMock(side_effect=mock_execute)
        storage = MagicMock()

        with patch(
            "loom.services.provenance._c2pa_available",
            return_value=True,
        ):
            await embed_provenance_in_export(
                session, str(_ASSET_ID), str(_CASE_ID), storage
            )

        # provenance record still created for unsupported format
        assert session.add.call_count >= 1


class TestSignManifestUnsupported:
    """sign_manifest returns None for unsupported formats."""

    def test_unsupported_format_returns_none(self) -> None:
        """application/pdf is not c2pa-supported."""
        manifest = {
            "claim_generator": CLAIM_GENERATOR,
            "format": "application/pdf",
        }

        with patch(
            "loom.services.provenance._c2pa_available",
            return_value=True,
        ):
            result = sign_manifest(
                manifest,
                "/tmp/in.pdf",  # noqa: S108
                "/tmp/out.pdf",  # noqa: S108
            )
        assert result is None

    def test_text_format_returns_none(self) -> None:
        """text/plain is not c2pa-supported."""
        manifest = {
            "claim_generator": CLAIM_GENERATOR,
            "format": "text/plain",
        }

        with patch(
            "loom.services.provenance._c2pa_available",
            return_value=True,
        ):
            result = sign_manifest(
                manifest,
                "/tmp/in.txt",  # noqa: S108
                "/tmp/out.txt",  # noqa: S108
            )
        assert result is None
