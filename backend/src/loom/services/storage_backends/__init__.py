"""storage backends for server and lite deployment profiles.

- server profile uses minio (``StorageService`` in ``services.storage``)
- lite profile uses the local filesystem with WORM semantics

both conform to :class:`StorageBackend`, a narrow protocol that
describes the operations loom callers actually use. new callers
should depend on the protocol, not a concrete class.
"""

from __future__ import annotations

from loom.config import Settings
from loom.services.storage_backends.base import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageBackend,
)
from loom.services.storage_backends.local import LocalStorageBackend

__all__ = [
    "DERIVATIVES_BUCKET",
    "ORIGINALS_BUCKET",
    "LocalStorageBackend",
    "StorageBackend",
    "build_storage_backend",
]


def build_storage_backend(settings: Settings) -> StorageBackend:
    """return the storage backend matching the deployment profile.

    lite -> LocalStorageBackend rooted at ``settings.resolved_data_dir()``.
    server -> a fresh ``StorageService`` wrapping a minio client.
    """
    if settings.is_lite:
        if not settings.storage_signing_secret:
            raise ValueError(
                "lite profile requires LOOM_STORAGE_SIGNING_SECRET "
                "(a random per-install value) to sign loopback "
                "presigned urls; see Settings.storage_signing_secret."
            )
        return LocalStorageBackend(
            settings.resolved_data_dir(),
            signing_secret=settings.storage_signing_secret,
        )

    # deferred import so lite deployments do not require minio.
    from minio import Minio

    from loom.services.storage import StorageService

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return StorageService(client)
