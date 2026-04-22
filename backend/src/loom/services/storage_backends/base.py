"""narrow protocol every storage backend must satisfy.

kept deliberately small: only the operations loom calls from
services, activities, and api routes. presigned-url semantics are
backend-specific and may be loopback URLs in lite profile.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

ORIGINALS_BUCKET = "loom-originals"
DERIVATIVES_BUCKET = "loom-derivatives"


@runtime_checkable
class StorageBackend(Protocol):
    """duck-typed contract for object storage.

    implementations: ``StorageService`` (minio) for server profile and
    ``LocalStorageBackend`` (filesystem, WORM) for lite profile.
    """

    def ensure_buckets(self) -> None:
        """create the originals + derivatives buckets if missing."""

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str,
    ) -> None: ...

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> None: ...

    def download_file(
        self,
        bucket: str,
        key: str,
        dest_path: str,
    ) -> None: ...

    def get_presigned_upload_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str: ...

    def get_presigned_download_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str: ...

    def object_exists(self, bucket: str, key: str) -> bool: ...

    def get_object_stream(
        self,
        bucket: str,
        key: str,
        chunk_size: int = 65536,
    ) -> tuple[int, Iterator[bytes]]: ...

    def delete_object(self, bucket: str, key: str) -> None:
        """remove an object. in lite profile this bypasses the WORM
        bit for callers that legitimately need deletion (e.g. soft
        delete purge). append-only custody is enforced at the db
        layer, not here."""
