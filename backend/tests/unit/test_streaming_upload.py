import hashlib
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

import loom.config
from loom.services.streaming_upload import (
    UploadTooLargeError,
    cleanup_stale_uploads,
    stream_to_tempfile,
)


class _FakeRequest:
    """duck-typed Request: only .stream() is consumed."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def stream(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@pytest.fixture
def lite_data_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("LOOM_DATA_DIR", str(tmp_path))
    loom.config.get_settings.cache_clear()
    yield tmp_path
    loom.config.get_settings.cache_clear()


async def test_streams_and_hashes_like_the_whole_file(
    lite_data_dir: Path,
) -> None:
    payload = b"a" * 10_000 + b"b" * 10_000
    chunks = [payload[i : i + 4096] for i in range(0, len(payload), 4096)]

    result = await stream_to_tempfile(_FakeRequest(chunks), max_bytes=0)

    assert result.size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.sha512 == hashlib.sha512(payload).hexdigest()
    assert result.path.read_bytes() == payload
    # head carries the first bytes for magic sniffing
    assert result.head == payload[:8192]
    result.path.unlink()


async def test_mid_stream_cap_removes_partial_file(
    lite_data_dir: Path,
) -> None:
    chunks = [b"x" * 1024] * 10

    with pytest.raises(UploadTooLargeError):
        await stream_to_tempfile(_FakeRequest(chunks), max_bytes=2048)

    tmp_dir = lite_data_dir / "tmp-uploads"
    assert list(tmp_dir.iterdir()) == []


async def test_zero_cap_means_unlimited(lite_data_dir: Path) -> None:
    result = await stream_to_tempfile(
        _FakeRequest([b"x" * 4096] * 4), max_bytes=0
    )
    assert result.size == 16_384
    result.path.unlink()


async def test_cleanup_reaps_only_stale_files(lite_data_dir: Path) -> None:
    tmp_dir = lite_data_dir / "tmp-uploads"
    tmp_dir.mkdir(parents=True)
    stale = tmp_dir / "upload-stale"
    fresh = tmp_dir / "upload-fresh"
    stale.write_bytes(b"old")
    fresh.write_bytes(b"new")
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(stale, (two_days_ago, two_days_ago))

    removed = cleanup_stale_uploads()

    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
