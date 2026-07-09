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


def attachment_content_disposition(filename: str) -> str:
    """build the ``Content-Disposition`` value forcing a download.

    the local serve route emits this header directly; the minio
    backend hands it to ``presigned_get_object`` as a signed
    ``response-content-disposition`` so it survives sigv4 verification.
    quotes and newlines are stripped so the quoted filename stays a
    valid header value.
    """
    safe = filename.replace('"', "").replace("\r", "").replace("\n", "")
    return f'attachment; filename="{safe}"'


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

    def upload_file_move(
        self,
        bucket: str,
        key: str,
        src_path: str,
        content_type: str,
    ) -> None:
        """move ``src_path`` into storage, consuming the source file.

        streamed uploads land in a temp file first; this avoids a
        second full copy when the destination shares a filesystem.
        """
        ...

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
        download_filename: str | None = None,
    ) -> str:
        """presign a download url.

        when ``download_filename`` is set, the response carries a
        ``Content-Disposition: attachment`` for that name, signed into
        the url so callers never append an unsigned query param (which
        breaks minio's sigv4 verification — see #322)."""
        ...

    def object_exists(self, bucket: str, key: str) -> bool: ...

    def get_object_stream(
        self,
        bucket: str,
        key: str,
        chunk_size: int = 65536,
    ) -> tuple[int, Iterator[bytes]]: ...

    def get_object_size(self, bucket: str, key: str) -> int:
        """return the object's size in bytes; raise if it is missing."""

    def get_object_range(
        self,
        bucket: str,
        key: str,
        start: int,
        end: int,
        chunk_size: int = 65536,
    ) -> Iterator[bytes]:
        """yield bytes [start, end] inclusive — backs HTTP Range reads."""

    def delete_object(self, bucket: str, key: str) -> None:
        """remove an object. in lite profile this bypasses the WORM
        bit for callers that legitimately need deletion (e.g. soft
        delete purge). append-only custody is enforced at the db
        layer, not here."""
