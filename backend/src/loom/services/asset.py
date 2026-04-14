"""asset service — soft delete, restore, and list queries."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.chain_of_custody import ChainOfCustodyEntry


async def soft_delete_asset(
    session: AsyncSession,
    asset_id: str,
    user_id: str,
    ip_address: str | None = None,
) -> Asset:
    """mark an asset as deleted and record custody entry.

    sets deleted_at and deleted_by, then appends a
    chain-of-custody record documenting the soft delete.
    """
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        msg = f"asset {asset_id} not found"
        raise ValueError(msg)

    if asset.deleted_at is not None:
        msg = f"asset {asset_id} is already deleted"
        raise ValueError(msg)

    now = datetime.now(UTC)
    asset.deleted_at = now
    asset.deleted_by = UUID(user_id)

    # append-only custody record
    entry = ChainOfCustodyEntry(
        asset_id=UUID(asset_id),
        action="soft_deleted",
        actor_id=UUID(user_id),
        detail={
            "action": "soft_deleted",
            "deleted_at": now.isoformat(),
            "deleted_by": user_id,
        },
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
    return asset


async def restore_asset(
    session: AsyncSession,
    asset_id: str,
    user_id: str,
    ip_address: str | None = None,
) -> Asset:
    """restore a soft-deleted asset (admin only).

    clears deleted_at/deleted_by and records a custody entry.
    """
    result = await session.execute(
        select(Asset).where(Asset.id == UUID(asset_id))
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        msg = f"asset {asset_id} not found"
        raise ValueError(msg)

    if asset.deleted_at is None:
        msg = f"asset {asset_id} is not deleted"
        raise ValueError(msg)

    asset.deleted_at = None
    asset.deleted_by = None

    entry = ChainOfCustodyEntry(
        asset_id=UUID(asset_id),
        action="restored",
        actor_id=UUID(user_id),
        detail={
            "action": "restored",
            "restored_by": user_id,
        },
        ip_address=ip_address,
    )
    session.add(entry)
    await session.flush()
    return asset


async def list_assets(
    session: AsyncSession,
    case_id: str,
    skip: int = 0,
    limit: int = 20,
    include_deleted: bool = False,
) -> tuple[list[Asset], int]:
    """list assets for a case, excluding soft-deleted by default.

    returns (assets, total_count).
    """
    base_filter = [Asset.case_id == UUID(case_id)]
    if not include_deleted:
        base_filter.append(Asset.deleted_at.is_(None))

    # total count
    count_q = select(func.count(Asset.id)).where(*base_filter)
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    # paginated query
    query = (
        select(Asset)
        .where(*base_filter)
        .offset(skip)
        .limit(limit)
        .order_by(Asset.created_at.desc())
    )
    result = await session.execute(query)
    assets = list(result.scalars().all())

    return assets, total


async def get_asset(
    session: AsyncSession,
    case_id: str,
    asset_id: str,
    include_deleted: bool = False,
) -> Asset | None:
    """get a single asset, excluding soft-deleted by default."""
    filters = [
        Asset.id == UUID(asset_id),
        Asset.case_id == UUID(case_id),
    ]
    if not include_deleted:
        filters.append(Asset.deleted_at.is_(None))

    result = await session.execute(select(Asset).where(*filters))
    return result.scalar_one_or_none()
