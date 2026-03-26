from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.asset import Asset
from loom.models.organization import SharedEvidenceLink
from loom.services.case import check_case_access


async def share_evidence(
    session: AsyncSession,
    source_case_id: str,
    target_case_id: str,
    asset_id: str,
    user_id: str,
    access_level: str = "view",
    expires_at: datetime | None = None,
) -> SharedEvidenceLink:
    """share an asset from one case to another.

    requires editor+ on source case. validates asset
    belongs to source case.
    """
    # verify editor+ on source case
    has_access = await check_case_access(
        session,
        source_case_id,
        user_id,
        required_role="editor",
    )
    if not has_access:
        msg = "insufficient access on source case"
        raise PermissionError(msg)

    # verify asset belongs to source case
    result = await session.execute(
        select(Asset).where(
            Asset.id == UUID(asset_id),
            Asset.case_id == UUID(source_case_id),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        msg = "asset not found in source case"
        raise ValueError(msg)

    link = SharedEvidenceLink(
        source_case_id=UUID(source_case_id),
        target_case_id=UUID(target_case_id),
        asset_id=UUID(asset_id),
        shared_by=UUID(user_id),
        access_level=access_level,
        expires_at=expires_at,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


async def list_shared_with_case(
    session: AsyncSession,
    case_id: str,
) -> list[SharedEvidenceLink]:
    """list evidence shared TO this case."""
    result = await session.execute(
        select(SharedEvidenceLink, Asset.original_filename)
        .join(
            Asset,
            Asset.id == SharedEvidenceLink.asset_id,
        )
        .where(
            SharedEvidenceLink.target_case_id == UUID(case_id),
        )
    )
    rows = result.all()
    links: list[SharedEvidenceLink] = []
    for row in rows:
        link = row[0]
        link.original_filename = row[1]
        links.append(link)
    return links


async def list_shared_from_case(
    session: AsyncSession,
    case_id: str,
) -> list[SharedEvidenceLink]:
    """list evidence shared FROM this case."""
    result = await session.execute(
        select(SharedEvidenceLink, Asset.original_filename)
        .join(
            Asset,
            Asset.id == SharedEvidenceLink.asset_id,
        )
        .where(
            SharedEvidenceLink.source_case_id == UUID(case_id),
        )
    )
    rows = result.all()
    links: list[SharedEvidenceLink] = []
    for row in rows:
        link = row[0]
        link.original_filename = row[1]
        links.append(link)
    return links


async def revoke_share(
    session: AsyncSession,
    link_id: str,
    case_id: str,
    user_id: str,
) -> bool:
    """revoke a shared evidence link (editor+ on source)."""
    result = await session.execute(
        select(SharedEvidenceLink).where(
            SharedEvidenceLink.id == UUID(link_id),
            SharedEvidenceLink.source_case_id == UUID(case_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        return False

    # verify editor+ on source case
    has_access = await check_case_access(
        session,
        case_id,
        user_id,
        required_role="editor",
    )
    if not has_access:
        msg = "insufficient access on source case"
        raise PermissionError(msg)

    await session.delete(link)
    await session.commit()
    return True


async def check_shared_access(
    session: AsyncSession,
    asset_id: str,
    case_id: str,
) -> bool:
    """check if an asset is shared with a case and not expired."""
    now = datetime.now(tz=UTC)
    result = await session.execute(
        select(SharedEvidenceLink).where(
            SharedEvidenceLink.asset_id == UUID(asset_id),
            SharedEvidenceLink.target_case_id == UUID(case_id),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        return False

    # check expiration
    return not (link.expires_at and link.expires_at < now)
