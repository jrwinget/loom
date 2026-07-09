"""stream request bodies to disk without buffering in memory.

the multipart parser re-buffers UploadFile content, so the raw-body
upload route streams chunks straight to a temp file, hashing
incrementally as they arrive. the temp dir lives inside the data
dir so the final move into the originals bucket is an atomic rename
on the lite profile.
"""

import hashlib
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from loom.config import get_settings

logger = logging.getLogger(__name__)

# enough for every magic-bytes signature validate_file_type checks
_HEAD_BYTES = 8192
_TMP_DIR_NAME = "tmp-uploads"
# stale temp files (a crashed upload) are reaped on startup once
# they are old enough that no in-flight request can still own them
_STALE_AFTER_S = 24 * 3600


class UploadTooLargeError(RuntimeError):
    """the streamed body exceeded the configured cap."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"upload exceeds the {limit} byte limit")
        self.limit = limit


@dataclass(frozen=True)
class StreamedUpload:
    path: Path
    size: int
    sha256: str
    sha512: str
    # first bytes of the body, for magic-bytes validation
    head: bytes


def upload_tmp_dir() -> Path:
    tmp = get_settings().resolved_data_dir() / _TMP_DIR_NAME
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def cleanup_stale_uploads() -> int:
    """remove temp files orphaned by a crash; returns count removed."""
    removed = 0
    cutoff = time.time() - _STALE_AFTER_S
    tmp = get_settings().resolved_data_dir() / _TMP_DIR_NAME
    if not tmp.is_dir():
        return 0
    for entry in tmp.iterdir():
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            logger.warning("could not reap %s", entry, exc_info=True)
    if removed:
        logger.info("reaped %d stale upload temp file(s)", removed)
    return removed


async def stream_to_tempfile(
    request: Request,
    max_bytes: int,
) -> StreamedUpload:
    """stream the raw request body to a temp file, hashing as it lands.

    ``max_bytes`` <= 0 disables the cap. the partial temp file is
    removed before any exception propagates, including a mid-stream
    cap violation (a lying Content-Length).
    """
    tmp_dir = upload_tmp_dir()
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    size = 0
    head = b""

    fd, name = tempfile.mkstemp(dir=tmp_dir, prefix="upload-")
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as out:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if max_bytes > 0 and size > max_bytes:
                    raise UploadTooLargeError(max_bytes)
                sha256.update(chunk)
                sha512.update(chunk)
                if len(head) < _HEAD_BYTES:
                    head += chunk[: _HEAD_BYTES - len(head)]
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

    return StreamedUpload(
        path=path,
        size=size,
        sha256=sha256.hexdigest(),
        sha512=sha512.hexdigest(),
        head=head,
    )
