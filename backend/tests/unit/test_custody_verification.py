"""unit tests for loom.services.custody_verification."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services.custody_verification import (
    export_custody_report,
    verify_asset_chain,
    verify_case_custody,
)

_ASSET_ID = str(uuid4())
_CASE_ID = str(uuid4())
_USER_ID = str(uuid4())
_NOW = datetime.now(tz=UTC)


def _mock_session() -> AsyncMock:
    """build a mock async session."""
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    return s


def _make_entry(
    action: str = "upload",
    timestamp: datetime | None = None,
    asset_id: str = _ASSET_ID,
) -> ChainOfCustodyEntry:
    """create a custody entry with given params."""
    entry = ChainOfCustodyEntry(
        asset_id=asset_id,
        action=action,
        actor_id=_USER_ID,
        timestamp=timestamp or _NOW,
    )
    # set an id for the entry
    entry.id = uuid4()
    return entry


def _scalars_result(items: list) -> MagicMock:
    """mock a session.execute result with scalars().all()."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _rows_result(rows: list) -> MagicMock:
    """mock a session.execute result with .all()."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    return mock_result


# ── verify_asset_chain ─────────────────────────────────────


class TestVerifyAssetChain:
    @pytest.mark.asyncio
    async def test_valid_chain(self) -> None:
        """a proper sequential chain should verify as valid."""
        session = _mock_session()
        entries = [
            _make_entry("upload", _NOW),
            _make_entry(
                "hash_verified",
                _NOW + timedelta(seconds=1),
            ),
            _make_entry(
                "metadata_extracted",
                _NOW + timedelta(seconds=2),
            ),
        ]
        session.execute.return_value = _scalars_result(entries)

        result = await verify_asset_chain(session, _ASSET_ID)

        assert result.is_valid is True
        assert result.entries_count == 3
        assert result.first_entry == _NOW
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_empty_chain(self) -> None:
        """an asset with no custody entries is invalid."""
        session = _mock_session()
        session.execute.return_value = _scalars_result([])

        result = await verify_asset_chain(session, _ASSET_ID)

        assert result.is_valid is False
        assert result.entries_count == 0
        assert len(result.issues) == 1
        assert result.issues[0].severity == "error"
        assert "no custody entries" in result.issues[0].description

    @pytest.mark.asyncio
    async def test_timestamp_inversion(self) -> None:
        """entries out of order should produce an error."""
        session = _mock_session()
        entries = [
            _make_entry("upload", _NOW),
            _make_entry(
                "hash_verified",
                _NOW - timedelta(seconds=5),
            ),
        ]
        session.execute.return_value = _scalars_result(entries)

        result = await verify_asset_chain(session, _ASSET_ID)

        assert result.is_valid is False
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) == 1
        assert "timestamp inversion" in errors[0].description

    @pytest.mark.asyncio
    async def test_non_upload_first_entry_warns(self) -> None:
        """first entry not being an upload generates a warning."""
        session = _mock_session()
        entries = [
            _make_entry("metadata_extracted", _NOW),
        ]
        session.execute.return_value = _scalars_result(entries)

        result = await verify_asset_chain(session, _ASSET_ID)

        # still valid (warning, not error)
        assert result.is_valid is True
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "first custody entry" in warnings[0].description

    @pytest.mark.asyncio
    async def test_single_upload_entry(self) -> None:
        """a single upload entry is a valid chain."""
        session = _mock_session()
        entries = [_make_entry("upload", _NOW)]
        session.execute.return_value = _scalars_result(entries)

        result = await verify_asset_chain(session, _ASSET_ID)

        assert result.is_valid is True
        assert result.entries_count == 1

    @pytest.mark.asyncio
    async def test_identical_timestamps_warn(self) -> None:
        """two entries with the same timestamp get a warning."""
        session = _mock_session()
        entries = [
            _make_entry("upload", _NOW),
            _make_entry("hash_verified", _NOW),
        ]
        session.execute.return_value = _scalars_result(entries)

        result = await verify_asset_chain(session, _ASSET_ID)

        # still valid (only a warning)
        assert result.is_valid is True
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) == 1
        assert "same timestamp" in warnings[0].description


# ── verify_case_custody ────────────────────────────────────


class TestVerifyCaseCustody:
    @pytest.mark.asyncio
    async def test_all_valid(self) -> None:
        """case with all valid chains reports correctly."""
        session = _mock_session()
        asset1 = uuid4()
        asset2 = uuid4()

        # first call: get asset ids
        # subsequent calls: custody entries for each asset
        entries_a1 = [
            _make_entry("upload", _NOW),
        ]
        entries_a1[0].asset_id = asset1
        entries_a2 = [
            _make_entry("upload", _NOW),
        ]
        entries_a2[0].asset_id = asset2

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # asset id query
                return _rows_result([(asset1,), (asset2,)])
            elif call_count == 2:
                return _scalars_result(entries_a1)
            else:
                return _scalars_result(entries_a2)

        session.execute = mock_execute

        result = await verify_case_custody(session, _CASE_ID)

        assert result.total_assets == 2
        assert result.valid_assets == 2
        assert result.invalid_assets == 0

    @pytest.mark.asyncio
    async def test_mixed_validity(self) -> None:
        """case with one valid and one invalid asset."""
        session = _mock_session()
        asset1 = uuid4()
        asset2 = uuid4()

        entries_a1 = [_make_entry("upload", _NOW)]
        entries_a1[0].asset_id = asset1
        # second asset: empty chain = invalid
        entries_a2: list[ChainOfCustodyEntry] = []

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _rows_result([(asset1,), (asset2,)])
            elif call_count == 2:
                return _scalars_result(entries_a1)
            else:
                return _scalars_result(entries_a2)

        session.execute = mock_execute

        result = await verify_case_custody(session, _CASE_ID)

        assert result.total_assets == 2
        assert result.valid_assets == 1
        assert result.invalid_assets == 1

    @pytest.mark.asyncio
    async def test_empty_case(self) -> None:
        """case with no assets."""
        session = _mock_session()
        session.execute.return_value = _rows_result([])

        result = await verify_case_custody(session, _CASE_ID)

        assert result.total_assets == 0
        assert result.valid_assets == 0
        assert result.invalid_assets == 0


# ── export_custody_report ──────────────────────────────────


class TestExportCustodyReport:
    @pytest.mark.asyncio
    async def test_produces_report(self) -> None:
        """should produce a complete report with asset info."""
        session = _mock_session()
        asset = Asset(
            case_id=_CASE_ID,
            original_filename="test.mp4",
            storage_key="key",
            media_type="video",
            mime_type="video/mp4",
            file_size_bytes=1024,
            sha256_hash="a" * 64,
            sha512_hash="b" * 128,
            uploaded_by=_USER_ID,
            uploaded_at=_NOW,
            upload_status="complete",
            processing_status="complete",
        )
        asset.id = uuid4()

        entries = [_make_entry("upload", _NOW)]

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # asset query
                r = MagicMock()
                r.scalar_one_or_none.return_value = asset
                return r
            else:
                # custody entries (called twice: report + verify)
                return _scalars_result(entries)

        session.execute = mock_execute

        report = await export_custody_report(session, str(asset.id))

        assert report.original_filename == "test.mp4"
        assert report.sha256_hash == "a" * 64
        assert report.sha512_hash == "b" * 128
        assert report.verification.is_valid is True
        assert len(report.chain) == 1
        assert report.report_version == "1.0"

    @pytest.mark.asyncio
    async def test_asset_not_found(self) -> None:
        """should raise ValueError for missing asset."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await export_custody_report(session, str(uuid4()))
