"""tests for integrity verification service."""

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from loom.schemas.integrity import (
    CaseIntegrityResult,
    CustodyEntryResponse,
    IntegrityResult,
)
from loom.services.hashing import compute_hashes_from_iterator
from loom.services.integrity import (
    IntegrityError,
    generate_integrity_report,
    verify_asset_integrity,
    verify_case_integrity,
)

_TEST_DATA = b"evidence file content for integrity testing"
_CHUNK_SIZE = 16
_ASSET_ID = "00000000-0000-0000-0000-000000000001"
_CASE_ID = "00000000-0000-0000-0000-000000000002"
_USER_ID = "00000000-0000-0000-0000-000000000003"


def _computed_hashes() -> tuple[str, str]:
    """return expected sha256, sha512 for _TEST_DATA."""
    return (
        hashlib.sha256(_TEST_DATA).hexdigest(),
        hashlib.sha512(_TEST_DATA).hexdigest(),
    )


def _make_asset(
    sha256: str | None = None,
    sha512: str | None = None,
) -> MagicMock:
    """create a mock asset with correct hashes by default."""
    expected_256, expected_512 = _computed_hashes()
    asset = MagicMock()
    asset.id = UUID(_ASSET_ID)
    asset.case_id = UUID(_CASE_ID)
    asset.original_filename = "protest_video.mp4"
    asset.storage_key = f"{_CASE_ID}/{_ASSET_ID}/protest_video.mp4"
    asset.media_type = "video"
    asset.mime_type = "video/mp4"
    asset.file_size_bytes = len(_TEST_DATA)
    asset.sha256_hash = sha256 or expected_256
    asset.sha512_hash = sha512 or expected_512
    asset.uploaded_by = UUID(_USER_ID)
    asset.uploaded_at = datetime(2025, 1, 1, tzinfo=UTC)
    return asset


def _mock_storage_stream() -> MagicMock:
    """mock StorageBackend.get_object_stream to yield chunks."""
    chunks = []
    for i in range(0, len(_TEST_DATA), _CHUNK_SIZE):
        chunks.append(_TEST_DATA[i : i + _CHUNK_SIZE])

    def get_object_stream(bucket: str, key: str, **kw: object):
        return len(_TEST_DATA), iter(chunks)

    return get_object_stream


def _make_storage(stream=None) -> MagicMock:
    """build a mock StorageBackend with a configured get_object_stream."""
    storage = MagicMock()
    storage.get_object_stream = stream or _mock_storage_stream()
    return storage


def _make_session(
    asset: MagicMock | None = None,
    assets: list[MagicMock] | None = None,
    custody_entries: list[MagicMock] | None = None,
) -> AsyncMock:
    """create a mock async session."""
    session = AsyncMock()

    # track calls to determine what query is being executed
    call_count = [0]

    async def execute_side_effect(query):
        result_mock = MagicMock()
        call_count[0] += 1

        if assets is not None and call_count[0] == 1:
            # first call returns list of assets (case query)
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = assets
            result_mock.scalars.return_value = scalars_mock
        elif custody_entries is not None:
            # custody chain query
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = custody_entries
            result_mock.scalars.return_value = scalars_mock
        else:
            # single asset query
            result_mock.scalar_one_or_none.return_value = asset
            result_mock.scalar_one.return_value = asset
        return result_mock

    session.execute = AsyncMock(side_effect=execute_side_effect)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


class TestComputeHashesFromIterator:
    """streaming hash computation from sync iterator."""

    def test_matches_direct_hash(self) -> None:
        """iterator hashing matches hashlib directly."""
        expected_256 = hashlib.sha256(_TEST_DATA).hexdigest()
        expected_512 = hashlib.sha512(_TEST_DATA).hexdigest()

        chunks = [
            _TEST_DATA[i : i + _CHUNK_SIZE]
            for i in range(0, len(_TEST_DATA), _CHUNK_SIZE)
        ]
        sha256, sha512 = compute_hashes_from_iterator(iter(chunks))

        assert sha256 == expected_256
        assert sha512 == expected_512

    def test_never_loads_full_file(self) -> None:
        """verify chunks are processed individually."""
        max_chunk_seen = 0
        original_chunks = [
            _TEST_DATA[i : i + _CHUNK_SIZE]
            for i in range(0, len(_TEST_DATA), _CHUNK_SIZE)
        ]

        def tracking_iterator():
            nonlocal max_chunk_seen
            for chunk in original_chunks:
                if len(chunk) > max_chunk_seen:
                    max_chunk_seen = len(chunk)
                yield chunk

        compute_hashes_from_iterator(tracking_iterator())

        # no single chunk should be the full file
        assert max_chunk_seen <= _CHUNK_SIZE
        assert max_chunk_seen < len(_TEST_DATA)

    def test_empty_iterator(self) -> None:
        """empty iterator returns hashes of empty bytes."""
        expected_256 = hashlib.sha256(b"").hexdigest()
        expected_512 = hashlib.sha512(b"").hexdigest()

        sha256, sha512 = compute_hashes_from_iterator(iter([]))
        assert sha256 == expected_256
        assert sha512 == expected_512


class TestVerifyAssetIntegrity:
    """verify_asset_integrity service function."""

    @pytest.mark.asyncio
    async def test_hash_match_passes(self) -> None:
        """matching hashes produce a passing result."""
        asset = _make_asset()
        session = _make_session(asset=asset)
        storage = _make_storage()

        result = await verify_asset_integrity(
            session, storage, _ASSET_ID, _USER_ID
        )

        assert result.sha256_match is True
        assert result.sha512_match is True
        assert result.asset_id == UUID(_ASSET_ID)
        assert result.filename == "protest_video.mp4"

    @pytest.mark.asyncio
    async def test_sha256_mismatch_detected(self) -> None:
        """tampered sha256 is detected."""
        asset = _make_asset(sha256="a" * 64)
        session = _make_session(asset=asset)
        storage = _make_storage()

        result = await verify_asset_integrity(
            session, storage, _ASSET_ID, _USER_ID
        )

        assert result.sha256_match is False
        assert result.sha512_match is True
        assert result.stored_sha256 == "a" * 64

    @pytest.mark.asyncio
    async def test_sha512_mismatch_detected(self) -> None:
        """tampered sha512 is detected."""
        asset = _make_asset(sha512="b" * 128)
        session = _make_session(asset=asset)
        storage = _make_storage()

        result = await verify_asset_integrity(
            session, storage, _ASSET_ID, _USER_ID
        )

        assert result.sha256_match is True
        assert result.sha512_match is False

    @pytest.mark.asyncio
    async def test_both_hashes_mismatch(self) -> None:
        """both hashes tampered are both detected."""
        asset = _make_asset(sha256="a" * 64, sha512="b" * 128)
        session = _make_session(asset=asset)
        storage = _make_storage()

        result = await verify_asset_integrity(
            session, storage, _ASSET_ID, _USER_ID
        )

        assert result.sha256_match is False
        assert result.sha512_match is False

    @pytest.mark.asyncio
    async def test_missing_asset_raises(self) -> None:
        """missing asset raises IntegrityError."""
        session = _make_session(asset=None)

        with pytest.raises(IntegrityError, match="not found"):
            await verify_asset_integrity(
                session, _make_storage(), _ASSET_ID, _USER_ID
            )

    @pytest.mark.asyncio
    async def test_missing_storage_object_raises(self) -> None:
        """missing file in minio raises IntegrityError."""
        from minio.error import S3Error

        asset = _make_asset()
        session = _make_session(asset=asset)
        storage = MagicMock()
        storage.get_object_stream.side_effect = S3Error(
            "NoSuchKey", "not found", "", "", "", ""
        )

        with pytest.raises(IntegrityError, match="cannot read"):
            await verify_asset_integrity(
                session,
                storage,
                _ASSET_ID,
                _USER_ID,
            )

    @pytest.mark.asyncio
    async def test_creates_custody_entry(self) -> None:
        """verification creates a custody entry."""
        asset = _make_asset()
        session = _make_session(asset=asset)
        storage = _make_storage()

        await verify_asset_integrity(session, storage, _ASSET_ID, _USER_ID)

        # session.add was called with a custody entry
        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert entry.action == "integrity_verification"
        assert entry.actor_id == UUID(_USER_ID)
        assert entry.detail["result"] == "pass"
        session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_failed_verification_custody_entry(
        self,
    ) -> None:
        """failed verification records failure in custody."""
        asset = _make_asset(sha256="a" * 64)
        session = _make_session(asset=asset)
        storage = _make_storage()

        await verify_asset_integrity(session, storage, _ASSET_ID, _USER_ID)

        entry = session.add.call_args[0][0]
        assert entry.detail["result"] == "fail"
        assert entry.detail["sha256_match"] is False

    @pytest.mark.asyncio
    async def test_ip_address_recorded(self) -> None:
        """ip address is stored in custody entry."""
        asset = _make_asset()
        session = _make_session(asset=asset)
        storage = _make_storage()

        await verify_asset_integrity(
            session,
            storage,
            _ASSET_ID,
            _USER_ID,
            ip_address="192.168.1.1",
        )

        entry = session.add.call_args[0][0]
        assert entry.ip_address == "192.168.1.1"


class TestVerifyCaseIntegrity:
    """verify_case_integrity aggregates per-asset results."""

    @pytest.mark.asyncio
    async def test_all_assets_pass(self) -> None:
        """all passing assets are counted correctly."""
        asset1 = _make_asset()
        asset2 = _make_asset()
        asset2.id = UUID("00000000-0000-0000-0000-000000000099")

        session = AsyncMock()
        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            result_mock = MagicMock()
            if call_count[0] == 1:
                # case assets query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [asset1, asset2]
                result_mock.scalars.return_value = scalars_mock
            else:
                # individual asset lookups
                if call_count[0] == 2:
                    result_mock.scalar_one_or_none.return_value = asset1
                else:
                    result_mock.scalar_one_or_none.return_value = asset2
            return result_mock

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()

        storage = _make_storage()

        result = await verify_case_integrity(
            session, storage, _CASE_ID, _USER_ID
        )

        assert result.case_id == UUID(_CASE_ID)
        assert result.total_assets == 2
        assert result.verified_count == 2
        assert result.passed_count == 2
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_mixed_results(self) -> None:
        """mix of passing and failing assets."""
        good_asset = _make_asset()
        bad_asset = _make_asset(sha256="a" * 64)
        bad_asset.id = UUID("00000000-0000-0000-0000-000000000099")

        session = AsyncMock()
        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            result_mock = MagicMock()
            if call_count[0] == 1:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [
                    good_asset,
                    bad_asset,
                ]
                result_mock.scalars.return_value = scalars_mock
            elif call_count[0] == 2:
                result_mock.scalar_one_or_none.return_value = good_asset
            else:
                result_mock.scalar_one_or_none.return_value = bad_asset
            return result_mock

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()
        storage = _make_storage()

        result = await verify_case_integrity(
            session, storage, _CASE_ID, _USER_ID
        )

        assert result.total_assets == 2
        assert result.passed_count == 1
        assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_empty_case(self) -> None:
        """case with no assets returns zero counts."""
        session = _make_session(assets=[])
        storage = _make_storage()

        result = await verify_case_integrity(
            session, storage, _CASE_ID, _USER_ID
        )

        assert result.total_assets == 0
        assert result.verified_count == 0
        assert result.passed_count == 0
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_storage_error_counts_as_failure(
        self,
    ) -> None:
        """asset unreadable from storage counts as failed."""
        from minio.error import S3Error

        asset = _make_asset()

        session = AsyncMock()
        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            result_mock = MagicMock()
            if call_count[0] == 1:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [asset]
                result_mock.scalars.return_value = scalars_mock
            else:
                result_mock.scalar_one_or_none.return_value = asset
            return result_mock

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()
        storage = MagicMock()
        storage.get_object_stream.side_effect = S3Error(
            "NoSuchKey", "not found", "", "", "", ""
        )

        result = await verify_case_integrity(
            session, storage, _CASE_ID, _USER_ID
        )

        assert result.total_assets == 1
        assert result.verified_count == 0
        assert result.failed_count == 1


class TestGenerateIntegrityReport:
    """generate_integrity_report produces court-ready output."""

    @pytest.mark.asyncio
    async def test_report_includes_all_sections(self) -> None:
        """report contains verification, custody, metadata."""
        asset = _make_asset()

        custody_entry = MagicMock()
        custody_entry.id = UUID("00000000-0000-0000-0000-000000000050")
        custody_entry.action = "upload"
        custody_entry.actor_id = UUID(_USER_ID)
        custody_entry.detail = {"action": "file_uploaded"}
        custody_entry.ip_address = "10.0.0.1"
        custody_entry.timestamp = datetime(2025, 1, 1, tzinfo=UTC)

        session = AsyncMock()
        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            result_mock = MagicMock()
            if call_count[0] == 1:
                # verify_asset_integrity fetches asset
                result_mock.scalar_one_or_none.return_value = asset
            elif call_count[0] == 2:
                # report fetches asset metadata
                result_mock.scalar_one.return_value = asset
            else:
                # custody chain query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [custody_entry]
                result_mock.scalars.return_value = scalars_mock
            return result_mock

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.add = MagicMock()
        session.flush = AsyncMock()
        storage = _make_storage()

        report = await generate_integrity_report(
            session, storage, _ASSET_ID, _USER_ID
        )

        assert report.asset_id == UUID(_ASSET_ID)
        assert report.case_id == UUID(_CASE_ID)
        assert report.original_filename == "protest_video.mp4"
        assert report.verification.sha256_match is True
        assert report.verification.sha512_match is True
        assert len(report.custody_chain) >= 1
        assert report.custody_chain[0].action == "upload"
        assert report.report_generated_at is not None


class TestIntegrityResultSchema:
    """schema validation tests."""

    def test_integrity_result_serialization(self) -> None:
        """IntegrityResult serializes correctly."""
        now = datetime.now(UTC)
        result = IntegrityResult(
            asset_id=UUID(_ASSET_ID),
            filename="test.mp4",
            storage_key="key/test.mp4",
            file_size=1024,
            stored_sha256="a" * 64,
            computed_sha256="a" * 64,
            stored_sha512="b" * 128,
            computed_sha512="b" * 128,
            sha256_match=True,
            sha512_match=True,
            verified_at=now,
        )
        data = result.model_dump()
        assert data["sha256_match"] is True
        assert data["asset_id"] == UUID(_ASSET_ID)

    def test_case_integrity_result_serialization(self) -> None:
        """CaseIntegrityResult serializes correctly."""
        result = CaseIntegrityResult(
            case_id=UUID(_CASE_ID),
            total_assets=5,
            verified_count=5,
            passed_count=4,
            failed_count=1,
            results=[],
        )
        data = result.model_dump()
        assert data["total_assets"] == 5
        assert data["failed_count"] == 1

    def test_custody_entry_response_optional_fields(
        self,
    ) -> None:
        """optional fields default to None."""
        entry = CustodyEntryResponse(
            id=UUID(_ASSET_ID),
            action="upload",
            actor_id=UUID(_USER_ID),
            timestamp=datetime.now(UTC),
        )
        assert entry.detail is None
        assert entry.ip_address is None
