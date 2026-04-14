"""unit tests for asset soft delete and restore."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry
from loom.services.asset import (
    get_asset,
    list_assets,
    restore_asset,
    soft_delete_asset,
)

_USER_ID = str(uuid4())
_CASE_ID = str(uuid4())
_ASSET_ID = str(uuid4())


def _mock_session() -> AsyncMock:
    """build a mock async session with standard helpers."""
    s = AsyncMock()
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    s.refresh = AsyncMock()
    s.delete = AsyncMock()
    return s


def _make_asset(
    deleted: bool = False,
) -> Asset:
    """create a test asset with optional soft-delete state."""
    asset = Asset(
        case_id=_CASE_ID,
        original_filename="test.mp4",
        storage_key=f"{_CASE_ID}/{_ASSET_ID}/test.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size_bytes=1024,
        sha256_hash="a" * 64,
        sha512_hash="b" * 128,
        upload_status="complete",
        uploaded_by=_USER_ID,
        processing_status="complete",
    )
    asset.id = _ASSET_ID  # type: ignore[assignment]
    if deleted:
        asset.deleted_at = datetime.now(UTC)
        asset.deleted_by = _USER_ID  # type: ignore[assignment]
    else:
        asset.deleted_at = None
        asset.deleted_by = None
    return asset


# -- soft_delete_asset -----------------------------------------------


class TestSoftDeleteAsset:
    @pytest.mark.asyncio
    async def test_sets_deleted_at_and_deleted_by(self) -> None:
        """soft delete sets timestamp and actor."""
        session = _mock_session()
        asset = _make_asset()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await soft_delete_asset(
            session,
            _ASSET_ID,
            _USER_ID,
        )
        assert result.deleted_at is not None
        assert str(result.deleted_by) == _USER_ID

    @pytest.mark.asyncio
    async def test_creates_custody_entry(self) -> None:
        """soft delete appends a chain-of-custody record."""
        session = _mock_session()
        asset = _make_asset()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        await soft_delete_asset(
            session,
            _ASSET_ID,
            _USER_ID,
            "10.0.0.1",
        )
        # session.add called once for the custody entry
        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert isinstance(entry, ChainOfCustodyEntry)
        assert entry.action == "soft_deleted"
        assert entry.ip_address == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_raises_if_not_found(self) -> None:
        """soft delete raises ValueError for missing asset."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await soft_delete_asset(
                session,
                _ASSET_ID,
                _USER_ID,
            )

    @pytest.mark.asyncio
    async def test_raises_if_already_deleted(self) -> None:
        """soft delete raises ValueError if already deleted."""
        session = _mock_session()
        asset = _make_asset(deleted=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="already deleted"):
            await soft_delete_asset(
                session,
                _ASSET_ID,
                _USER_ID,
            )


# -- restore_asset ---------------------------------------------------


class TestRestoreAsset:
    @pytest.mark.asyncio
    async def test_clears_deleted_at(self) -> None:
        """restore clears the soft-delete marker."""
        session = _mock_session()
        asset = _make_asset(deleted=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await restore_asset(
            session,
            _ASSET_ID,
            _USER_ID,
        )
        assert result.deleted_at is None
        assert result.deleted_by is None

    @pytest.mark.asyncio
    async def test_creates_custody_entry(self) -> None:
        """restore appends a chain-of-custody record."""
        session = _mock_session()
        asset = _make_asset(deleted=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        await restore_asset(
            session,
            _ASSET_ID,
            _USER_ID,
            "10.0.0.1",
        )
        session.add.assert_called_once()
        entry = session.add.call_args[0][0]
        assert isinstance(entry, ChainOfCustodyEntry)
        assert entry.action == "restored"

    @pytest.mark.asyncio
    async def test_raises_if_not_found(self) -> None:
        """restore raises ValueError for missing asset."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await restore_asset(
                session,
                _ASSET_ID,
                _USER_ID,
            )

    @pytest.mark.asyncio
    async def test_raises_if_not_deleted(self) -> None:
        """restore raises ValueError if asset is not deleted."""
        session = _mock_session()
        asset = _make_asset(deleted=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="is not deleted"):
            await restore_asset(
                session,
                _ASSET_ID,
                _USER_ID,
            )


# -- list_assets -----------------------------------------------------


class TestListAssets:
    @pytest.mark.asyncio
    async def test_excludes_deleted_by_default(self) -> None:
        """list_assets filters out soft-deleted assets."""
        session = _mock_session()
        active = _make_asset(deleted=False)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [active]
        data_result = MagicMock()
        data_result.scalars.return_value = scalars_mock
        session.execute.side_effect = [
            count_result,
            data_result,
        ]

        assets, total = await list_assets(
            session,
            _CASE_ID,
        )
        assert total == 1
        assert len(assets) == 1
        assert assets[0].deleted_at is None

    @pytest.mark.asyncio
    async def test_includes_deleted_with_flag(self) -> None:
        """list_assets includes soft-deleted when asked."""
        session = _mock_session()
        active = _make_asset(deleted=False)
        deleted = _make_asset(deleted=True)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [active, deleted]
        data_result = MagicMock()
        data_result.scalars.return_value = scalars_mock
        session.execute.side_effect = [
            count_result,
            data_result,
        ]

        assets, total = await list_assets(
            session,
            _CASE_ID,
            include_deleted=True,
        )
        assert total == 2
        assert len(assets) == 2


# -- get_asset -------------------------------------------------------


class TestGetAsset:
    @pytest.mark.asyncio
    async def test_returns_active_asset(self) -> None:
        """get_asset returns non-deleted asset."""
        session = _mock_session()
        asset = _make_asset(deleted=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await get_asset(
            session,
            _CASE_ID,
            _ASSET_ID,
        )
        assert result is asset

    @pytest.mark.asyncio
    async def test_returns_none_for_deleted(self) -> None:
        """get_asset hides deleted assets by default."""
        session = _mock_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await get_asset(
            session,
            _CASE_ID,
            _ASSET_ID,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_include_deleted_returns_asset(self) -> None:
        """get_asset with include_deleted finds deleted."""
        session = _mock_session()
        asset = _make_asset(deleted=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = asset
        session.execute.return_value = mock_result

        result = await get_asset(
            session,
            _CASE_ID,
            _ASSET_ID,
            include_deleted=True,
        )
        assert result is asset
