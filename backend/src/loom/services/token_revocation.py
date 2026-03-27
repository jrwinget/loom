from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.revoked_token import RevokedToken


async def revoke_token(
    session: AsyncSession,
    jti: str,
    user_id: str,
    expires_at: datetime,
) -> None:
    """revoke a single token by jti."""
    # skip if already revoked
    result = await session.execute(
        select(RevokedToken.id).where(RevokedToken.jti == jti)
    )
    if result.scalar_one_or_none() is not None:
        return

    entry = RevokedToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at,
    )
    session.add(entry)
    await session.commit()


async def is_token_revoked(
    session: AsyncSession,
    jti: str,
) -> bool:
    """check if a token jti has been revoked."""
    result = await session.execute(
        select(RevokedToken.id).where(RevokedToken.jti == jti)
    )
    return result.scalar_one_or_none() is not None


async def cleanup_expired_tokens(
    session: AsyncSession,
) -> int:
    """purge revoked tokens that have already expired.

    returns the number of rows deleted.
    """
    now = datetime.now(UTC)
    cursor = await session.execute(
        delete(RevokedToken).where(RevokedToken.expires_at < now)
    )
    await session.commit()
    count: int = cursor.rowcount  # type: ignore[attr-defined]
    return count
