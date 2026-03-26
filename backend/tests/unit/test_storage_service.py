"""tests for storage service."""

from unittest.mock import MagicMock

from minio.error import S3Error

from loom.services.storage import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageService,
)


def _make_storage() -> tuple[StorageService, MagicMock]:
    """create storage service with mocked minio client."""
    client = MagicMock()
    return StorageService(client), client


class TestUploadFile:
    """upload_file delegates to minio fput_object."""

    def test_calls_fput_object(self) -> None:
        """uploads file from disk."""
        storage, client = _make_storage()
        storage.upload_file(
            ORIGINALS_BUCKET,
            "key.mp4",
            "/tmp/file.mp4",  # noqa: S108
            "video/mp4",
        )
        client.fput_object.assert_called_once_with(
            ORIGINALS_BUCKET,
            "key.mp4",
            "/tmp/file.mp4",  # noqa: S108
            content_type="video/mp4",
        )


class TestUploadBytes:
    """upload_bytes delegates to minio put_object."""

    def test_calls_put_object(self) -> None:
        """uploads raw bytes."""
        storage, client = _make_storage()
        data = b"hello world"
        storage.upload_bytes(ORIGINALS_BUCKET, "key.txt", data, "text/plain")
        client.put_object.assert_called_once()
        args = client.put_object.call_args
        assert args[0][0] == ORIGINALS_BUCKET
        assert args[0][1] == "key.txt"
        # length kwarg
        assert args[1]["length"] == len(data)
        assert args[1]["content_type"] == "text/plain"


class TestDownloadFile:
    """download_file delegates to minio fget_object."""

    def test_calls_fget_object(self) -> None:
        """downloads to disk."""
        storage, client = _make_storage()
        storage.download_file(
            ORIGINALS_BUCKET,
            "key.mp4",
            "/tmp/out.mp4",  # noqa: S108
        )
        client.fget_object.assert_called_once_with(
            ORIGINALS_BUCKET,
            "key.mp4",
            "/tmp/out.mp4",  # noqa: S108
        )


class TestPresignedUrls:
    """presigned url generation."""

    def test_upload_url(self) -> None:
        """generates presigned upload url."""
        storage, client = _make_storage()
        client.presigned_put_object.return_value = "https://minio/upload"
        url = storage.get_presigned_upload_url(ORIGINALS_BUCKET, "key.mp4")
        assert url == "https://minio/upload"
        client.presigned_put_object.assert_called_once()

    def test_download_url(self) -> None:
        """generates presigned download url."""
        storage, client = _make_storage()
        client.presigned_get_object.return_value = "https://minio/download"
        url = storage.get_presigned_download_url(ORIGINALS_BUCKET, "key.mp4")
        assert url == "https://minio/download"
        client.presigned_get_object.assert_called_once()

    def test_custom_expiry(self) -> None:
        """custom expiry passed to minio."""
        from datetime import timedelta

        storage, client = _make_storage()
        storage.get_presigned_upload_url(
            ORIGINALS_BUCKET, "key.mp4", expires=1800
        )
        args = client.presigned_put_object.call_args
        assert args[1]["expires"] == timedelta(seconds=1800)


class TestObjectExists:
    """object_exists checks stat_object."""

    def test_returns_true_when_exists(self) -> None:
        """returns True when object exists."""
        storage, client = _make_storage()
        client.stat_object.return_value = MagicMock()
        assert storage.object_exists(ORIGINALS_BUCKET, "key.mp4") is True

    def test_returns_false_on_s3_error(self) -> None:
        """returns False when S3Error raised."""
        storage, client = _make_storage()
        client.stat_object.side_effect = S3Error(
            "NoSuchKey", "not found", "", "", "", ""
        )
        assert storage.object_exists(ORIGINALS_BUCKET, "missing") is False


class TestEnsureBuckets:
    """ensure_buckets creates missing buckets."""

    def test_creates_missing_buckets(self) -> None:
        """creates both buckets when they don't exist."""
        storage, client = _make_storage()
        client.bucket_exists.return_value = False
        storage.ensure_buckets()
        assert client.make_bucket.call_count == 2
        client.make_bucket.assert_any_call(ORIGINALS_BUCKET)
        client.make_bucket.assert_any_call(DERIVATIVES_BUCKET)

    def test_skips_existing_buckets(self) -> None:
        """does not create buckets that already exist."""
        storage, client = _make_storage()
        client.bucket_exists.return_value = True
        storage.ensure_buckets()
        client.make_bucket.assert_not_called()

    def test_mixed_existence(self) -> None:
        """creates only missing bucket."""
        storage, client = _make_storage()
        client.bucket_exists.side_effect = [True, False]
        storage.ensure_buckets()
        assert client.make_bucket.call_count == 1
        client.make_bucket.assert_called_once_with(DERIVATIVES_BUCKET)


class TestDeleteObject:
    """delete_object delegates to remove_object."""

    def test_calls_remove_object(self) -> None:
        """delegates to minio remove_object."""
        storage, client = _make_storage()
        storage.delete_object(ORIGINALS_BUCKET, "key.mp4")
        client.remove_object.assert_called_once_with(
            ORIGINALS_BUCKET, "key.mp4"
        )
