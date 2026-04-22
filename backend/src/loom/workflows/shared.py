"""shared infrastructure for temporal activities.

provides a cached async engine, session factory, and minio
client so activities avoid creating connections per call.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from minio import Minio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from loom.config import get_settings
from loom.services.storage_backends import (
    StorageBackend,
    build_storage_backend,
)

logger = logging.getLogger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_minio_client: Minio | None = None
_storage_backend: StorageBackend | None = None


def _get_engine() -> "AsyncEngine":
    """return cached async engine, creating on first call."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
            pool_timeout=settings.db_pool_timeout,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """return cached session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """yield an async session for use in activities."""
    factory = _get_session_factory()
    async with factory() as session:
        yield session


def get_minio_client() -> Minio:
    """return cached minio client.

    retained for tests that patch this symbol. production activity
    code should call :func:`get_storage_backend` instead so the lite
    profile works without minio — see issue #58.
    """
    global _minio_client
    if _minio_client is None:
        settings = get_settings()
        _minio_client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _minio_client


def get_storage_backend() -> StorageBackend:
    """return the cached storage backend for the active profile.

    on first call ``build_storage_backend(settings)`` is invoked;
    the result (server -> minio-backed ``StorageService``; lite ->
    ``LocalStorageBackend``) is reused for every subsequent call in
    this worker process. this mirrors the ``app.state.storage_backend``
    pattern used by the FastAPI app.
    """
    global _storage_backend
    if _storage_backend is None:
        _storage_backend = build_storage_backend(get_settings())
    return _storage_backend


async def dispose_engine() -> None:
    """dispose the cached engine. call on worker shutdown."""
    global _engine, _session_factory, _minio_client, _storage_backend
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
    _minio_client = None
    _storage_backend = None


def reset_for_testing() -> None:
    """reset module-level caches for test isolation."""
    global _engine, _session_factory, _minio_client, _storage_backend
    _engine = None
    _session_factory = None
    _minio_client = None
    _storage_backend = None
