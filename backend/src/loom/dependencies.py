from collections.abc import AsyncIterator

from fastapi import Request
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import Settings
from loom.config import get_settings as _get_settings


async def get_db_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    """yield a database session from the app state factory."""
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


def get_minio_client(request: Request) -> Minio:
    """return the minio client from app state."""
    return request.app.state.minio_client  # type: ignore[no-any-return]


def get_settings() -> Settings:
    """return the settings singleton."""
    return _get_settings()
