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
