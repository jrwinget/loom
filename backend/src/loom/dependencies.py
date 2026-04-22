import logging
from collections.abc import AsyncIterator

from fastapi import Request
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import Settings
from loom.config import get_settings as _get_settings
from loom.services.storage_backends import StorageBackend

logger = logging.getLogger(__name__)


async def get_db_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    """yield a database session from the app state factory.

    rolls back the transaction on unhandled exceptions to
    prevent partial writes from reaching the database.
    """
    session_factory = request.app.state.db_session_factory
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            logger.exception("rolling back session due to error")
            await session.rollback()
            raise


def get_minio_client(request: Request) -> Minio:
    """return the minio client from app state.

    kept for the health endpoint and a handful of server-profile-only
    code paths. route handlers should depend on ``get_storage_backend``
    instead so the lite profile works transparently — see issue #58.
    """
    return request.app.state.minio_client  # type: ignore[no-any-return]


def get_storage_backend(request: Request) -> StorageBackend:
    """return the storage backend from app state.

    the backend is built once in the lifespan via
    ``build_storage_backend(settings)`` so all requests share a
    single instance (and, on server profile, a single minio client).
    """
    return request.app.state.storage_backend  # type: ignore[no-any-return]


def get_settings() -> Settings:
    """return the settings singleton."""
    return _get_settings()
