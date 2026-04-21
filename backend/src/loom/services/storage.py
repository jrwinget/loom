import io
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from minio import Minio
from minio.error import S3Error


def _stream_chunks(
    response: Any,
    chunk_size: int,
) -> Iterator[bytes]:
    """yield chunks from a minio response, then close it."""
    try:
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        response.close()
        response.release_conn()


ORIGINALS_BUCKET = "loom-originals"
DERIVATIVES_BUCKET = "loom-derivatives"


class StorageService:
    """minio abstraction for object storage."""

    def __init__(self, client: Minio) -> None:
        self._client = client

    def ensure_buckets(self) -> None:
        """create loom-originals and loom-derivatives if missing."""
        for bucket in (ORIGINALS_BUCKET, DERIVATIVES_BUCKET):
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_path: str,
        content_type: str,
    ) -> None:
        """upload a file from disk to minio."""
        self._client.fput_object(
            bucket,
            key,
            file_path,
            content_type=content_type,
        )

    def upload_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        """upload bytes to minio."""
        self._client.put_object(
            bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def download_file(
        self,
        bucket: str,
        key: str,
        dest_path: str,
    ) -> None:
        """download an object from minio to disk."""
        self._client.fget_object(bucket, key, dest_path)

    def get_presigned_upload_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str:
        """generate a presigned url for uploading."""
        return self._client.presigned_put_object(
            bucket,
            key,
            expires=timedelta(seconds=expires),
        )

    def get_presigned_download_url(
        self,
        bucket: str,
        key: str,
        expires: int = 900,
    ) -> str:
        """generate a presigned url for downloading."""
        return self._client.presigned_get_object(
            bucket,
            key,
            expires=timedelta(seconds=expires),
        )

    def object_exists(self, bucket: str, key: str) -> bool:
        """check if an object exists in minio."""
        try:
            self._client.stat_object(bucket, key)
        except S3Error:
            return False
        return True

    def get_object_stream(
        self,
        bucket: str,
        key: str,
        chunk_size: int = 65536,
    ) -> tuple[int, "Iterator[bytes]"]:
        """stream an object from minio in chunks.

        returns (file_size, chunk_iterator). caller must
        close the response when done.
        """
        response = self._client.get_object(bucket, key)
        size = int(response.headers.get("Content-Length", 0))
        return size, _stream_chunks(response, chunk_size)

    def delete_object(self, bucket: str, key: str) -> None:
        """delete an object from minio."""
        self._client.remove_object(bucket, key)
