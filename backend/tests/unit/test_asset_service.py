"""unit tests for asset service — soft delete, restore, list."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from loom.models.asset import Asset
from loom.services.asset import (
    get_asset,
    list_assets,
    restore_asset,
    soft_delete_asset,
)

_ASSET_ID = str(uuid4())
_USER_ID = str(uuid4())
_CASE_ID = str(uuid4())
_NOW = datetime(2025, 6, 1, tzinfo=UTC)


def _make_session(
    *,
    asset: Asset | None = None,
) -> AsyncMock:
    """build a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()

    result = MagicMock()
    result.scalar_one_or_none.return_value = asset
    session.execute.return_value = result

    return session


def _make_asset(
    *,
    deleted: bool = False,
) -> MagicMock:
    mock = MagicMock(spec=Asset)
    mock.id = UUID(_ASSET_ID)
    mock.case_id = UUID(_CASE_ID)
    mock.original_filename = "test.mp4"
    mock.media_type = "video"
    mock.deleted_at = _NOW if deleted else None
    mock.deleted_by = UUID(_USER_ID) if deleted else None
    mock.created_at = _NOW
    return mock


@pytest.mark.asyncio
async def test_soft_delete_asset() -> None:
    """soft_delete_asset sets deleted_at and records custody."""
    asset = _make_asset(deleted=False)
    session = _make_session(asset=asset)

    result = await soft_delete_asset(session, _ASSET_ID, _USER_ID)

    assert result.deleted_at is not None
    assert result.deleted_by == UUID(_USER_ID)
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_asset_not_found() -> None:
    """soft_delete_asset raises ValueError for missing asset."""
    session = _make_session(asset=None)

    with pytest.raises(ValueError, match="not found"):
        await soft_delete_asset(session, _ASSET_ID, _USER_ID)


@pytest.mark.asyncio
async def test_soft_delete_already_deleted() -> None:
    """soft_delete_asset raises ValueError for already-deleted."""
    asset = _make_asset(deleted=True)
    session = _make_session(asset=asset)

    with pytest.raises(ValueError, match="already deleted"):
        await soft_delete_asset(session, _ASSET_ID, _USER_ID)


@pytest.mark.asyncio
async def test_restore_asset() -> None:
    """restore_asset clears deleted_at and records custody."""
    asset = _make_asset(deleted=True)
    session = _make_session(asset=asset)

    result = await restore_asset(session, _ASSET_ID, _USER_ID)

    assert result.deleted_at is None
    assert result.deleted_by is None
    session.add.assert_called_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_asset_not_found() -> None:
    """restore_asset raises ValueError for missing asset."""
    session = _make_session(asset=None)

    with pytest.raises(ValueError, match="not found"):
        await restore_asset(session, _ASSET_ID, _USER_ID)


@pytest.mark.asyncio
async def test_restore_asset_not_deleted() -> None:
    """restore_asset raises ValueError for non-deleted asset."""
    asset = _make_asset(deleted=False)
    session = _make_session(asset=asset)

    with pytest.raises(ValueError, match="is not deleted"):
        await restore_asset(session, _ASSET_ID, _USER_ID)


@pytest.mark.asyncio
async def test_list_assets() -> None:
    """list_assets returns assets and count."""
    asset = _make_asset()
    session = AsyncMock()

    # first call: count query
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    # second call: data query
    data_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = [asset]
    data_result.scalars.return_value = scalars

    session.execute.side_effect = [count_result, data_result]

    assets, total = await list_assets(session, _CASE_ID)

    assert total == 1
    assert len(assets) == 1
    assert assets[0].id == UUID(_ASSET_ID)


@pytest.mark.asyncio
async def test_list_assets_empty() -> None:
    """list_assets returns empty when no assets."""
    session = AsyncMock()

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    data_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    data_result.scalars.return_value = scalars

    session.execute.side_effect = [count_result, data_result]

    assets, total = await list_assets(session, _CASE_ID)

    assert total == 0
    assert len(assets) == 0


@pytest.mark.asyncio
async def test_get_asset() -> None:
    """get_asset returns asset when found."""
    asset = _make_asset()
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = asset
    session.execute.return_value = result

    found = await get_asset(session, _CASE_ID, _ASSET_ID)
    assert found is not None
    assert found.id == UUID(_ASSET_ID)


@pytest.mark.asyncio
async def test_get_asset_not_found() -> None:
    """get_asset returns None when not found."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    found = await get_asset(session, _CASE_ID, _ASSET_ID)
    assert found is None


@pytest.mark.asyncio
async def test_soft_delete_records_ip() -> None:
    """soft_delete_asset records ip in custody entry."""
    asset = _make_asset(deleted=False)
    session = _make_session(asset=asset)

    await soft_delete_asset(session, _ASSET_ID, _USER_ID, ip_address="10.0.0.1")

    # verify the custody entry was created with ip
    add_call = session.add.call_args[0][0]
    assert add_call.ip_address == "10.0.0.1"
