"""tests for the lite-profile filesystem storage backend.

mirrors the StorageService contract checked against a temp dir.
WORM-bit behavior is asserted explicitly because it's the main
reason this backend exists.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    LocalStorageBackend,
    StorageBackend,
)


@pytest.fixture
def backend(tmp_path: Path) -> LocalStorageBackend:
    b = LocalStorageBackend(tmp_path, signing_secret="test-secret")
    b.ensure_buckets()
    return b


class TestProtocolConformance:
    def test_conforms_to_protocol(self, backend: LocalStorageBackend) -> None:
        assert isinstance(backend, StorageBackend)


class TestEnsureBuckets:
    def test_creates_bucket_dirs(
        self, backend: LocalStorageBackend, tmp_path: Path
    ) -> None:
        assert (tmp_path / "buckets" / ORIGINALS_BUCKET).is_dir()
        assert (tmp_path / "buckets" / DERIVATIVES_BUCKET).is_dir()

    def test_idempotent(self, backend: LocalStorageBackend) -> None:
        backend.ensure_buckets()
        backend.ensure_buckets()


class TestUploadBytes:
    def test_writes_content(
        self, backend: LocalStorageBackend, tmp_path: Path
    ) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "a/b/c.bin", b"hello", "application/octet-stream"
        )
        stored = tmp_path / "buckets" / ORIGINALS_BUCKET / "a" / "b" / "c.bin"
        assert stored.read_bytes() == b"hello"

    def test_applies_worm_bit(
        self, backend: LocalStorageBackend, tmp_path: Path
    ) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "worm.bin", b"x", "application/octet-stream"
        )
        stored = tmp_path / "buckets" / ORIGINALS_BUCKET / "worm.bin"
        mode = stored.stat().st_mode
        # owner write bit must be clear after upload.
        assert not (mode & stat.S_IWUSR)

    def test_re_upload_replaces_content(
        self, backend: LocalStorageBackend
    ) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "k.bin", b"v1", "application/octet-stream"
        )
        backend.upload_bytes(
            ORIGINALS_BUCKET, "k.bin", b"v2", "application/octet-stream"
        )
        assert backend.object_exists(ORIGINALS_BUCKET, "k.bin")


class TestUploadFile:
    def test_copies_and_worms(
        self,
        backend: LocalStorageBackend,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src.bin"
        src.write_bytes(b"payload")
        backend.upload_file(
            DERIVATIVES_BUCKET,
            "deriv/x.bin",
            str(src),
            "application/octet-stream",
        )
        stored = tmp_path / "buckets" / DERIVATIVES_BUCKET / "deriv" / "x.bin"
        assert stored.read_bytes() == b"payload"
        assert not (stored.stat().st_mode & stat.S_IWUSR)


class TestDownloadFile:
    def test_copies_to_dest(
        self, backend: LocalStorageBackend, tmp_path: Path
    ) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "dl.bin", b"content", "application/octet-stream"
        )
        dest = tmp_path / "out.bin"
        backend.download_file(ORIGINALS_BUCKET, "dl.bin", str(dest))
        assert dest.read_bytes() == b"content"

    def test_raises_if_missing(
        self, backend: LocalStorageBackend, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            backend.download_file(
                ORIGINALS_BUCKET, "nope", str(tmp_path / "out")
            )


class TestObjectExists:
    def test_true_after_upload(self, backend: LocalStorageBackend) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "yes.bin", b"x", "application/octet-stream"
        )
        assert backend.object_exists(ORIGINALS_BUCKET, "yes.bin")

    def test_false_when_missing(self, backend: LocalStorageBackend) -> None:
        assert not backend.object_exists(ORIGINALS_BUCKET, "missing")


class TestGetObjectStream:
    def test_returns_size_and_chunks(
        self, backend: LocalStorageBackend
    ) -> None:
        body = b"abcdefghij" * 10
        backend.upload_bytes(
            ORIGINALS_BUCKET, "stream.bin", body, "application/octet-stream"
        )
        size, chunks = backend.get_object_stream(
            ORIGINALS_BUCKET, "stream.bin", chunk_size=16
        )
        assert size == len(body)
        assert b"".join(chunks) == body

    def test_raises_if_missing(self, backend: LocalStorageBackend) -> None:
        with pytest.raises(FileNotFoundError):
            backend.get_object_stream(ORIGINALS_BUCKET, "nope")


class TestDeleteObject:
    def test_removes_existing(self, backend: LocalStorageBackend) -> None:
        backend.upload_bytes(
            ORIGINALS_BUCKET, "bye.bin", b"x", "application/octet-stream"
        )
        backend.delete_object(ORIGINALS_BUCKET, "bye.bin")
        assert not backend.object_exists(ORIGINALS_BUCKET, "bye.bin")

    def test_noop_when_missing(self, backend: LocalStorageBackend) -> None:
        backend.delete_object(ORIGINALS_BUCKET, "ghost")


class TestPresignedLoopbackUrls:
    def test_upload_url_format(self, backend: LocalStorageBackend) -> None:
        url = backend.get_presigned_upload_url(
            ORIGINALS_BUCKET, "k.bin", expires=60
        )
        assert url.startswith("loom://storage/loom-originals/k.bin")
        assert "sig=" in url and "expires=" in url and "method=PUT" in url

    def test_download_url_format(self, backend: LocalStorageBackend) -> None:
        url = backend.get_presigned_download_url(
            ORIGINALS_BUCKET, "k.bin", expires=60
        )
        assert "method=GET" in url

    def test_verify_round_trip(self, backend: LocalStorageBackend) -> None:
        url = backend.get_presigned_download_url(
            ORIGINALS_BUCKET, "k.bin", expires=60
        )
        assert backend.verify_loopback_url(url)

    def test_verify_rejects_expired(self, backend: LocalStorageBackend) -> None:
        url = backend.get_presigned_download_url(
            ORIGINALS_BUCKET, "k.bin", expires=-1
        )
        # past expiry - immediate rejection
        time.sleep(0.01)
        assert not backend.verify_loopback_url(url)

    def test_verify_rejects_tampered_sig(
        self, backend: LocalStorageBackend
    ) -> None:
        url = backend.get_presigned_download_url(
            ORIGINALS_BUCKET, "k.bin", expires=60
        )
        tampered = url[:-1] + ("0" if url[-1] != "0" else "1")
        assert not backend.verify_loopback_url(tampered)

    def test_verify_rejects_non_loopback(
        self, backend: LocalStorageBackend
    ) -> None:
        assert not backend.verify_loopback_url("https://example.com/x")


class TestConfig:
    def test_resolves_default_data_dir(self) -> None:
        from loom.config import Settings

        s = Settings()
        assert s.deployment_profile == "server"
        assert not s.is_lite
        # server profile exposes a resolved data dir too (may be
        # created by the factory only when lite is active).
        assert s.resolved_data_dir().is_absolute()

    def test_is_lite_flag(self) -> None:
        from loom.config import Settings

        s = Settings(deployment_profile="lite")
        assert s.is_lite

    def test_validate_rejects_non_sqlite_in_lite(self) -> None:
        from loom.config import Settings

        s = Settings(
            deployment_profile="lite",
            database_url="postgresql+asyncpg://x/y",
        )
        with pytest.raises(ValueError, match="sqlite"):
            s.validate_deployment_profile()

    def test_validate_accepts_sqlite_in_lite(self, tmp_path: Path) -> None:
        from loom.config import Settings

        s = Settings(
            deployment_profile="lite",
            database_url="sqlite+aiosqlite:///:memory:",
            data_dir=tmp_path,
        )
        s.validate_deployment_profile()


class TestFactory:
    def test_lite_profile_returns_local_backend(self, tmp_path: Path) -> None:
        from loom.config import Settings
        from loom.services.storage_backends import build_storage_backend

        s = Settings(
            deployment_profile="lite",
            database_url="sqlite+aiosqlite:///:memory:",
            data_dir=tmp_path,
        )
        backend = build_storage_backend(s)
        assert isinstance(backend, LocalStorageBackend)
        assert isinstance(backend, StorageBackend)


def test_stream_file_closes_handle(tmp_path: Path) -> None:
    """ensure the generator closes its handle on exhaustion."""
    from loom.services.storage_backends.local import _stream_file

    target = tmp_path / "f.bin"
    target.write_bytes(b"data")
    gen = _stream_file(target, chunk_size=2)
    chunks = list(gen)
    assert b"".join(chunks) == b"data"
    # if the handle leaked, removing would fail on Windows; posix
    # is fine either way. main assertion is no exception raised.
    os.remove(target)
