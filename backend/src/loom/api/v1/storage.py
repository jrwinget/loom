"""storage management endpoints for the lite (desktop) profile.

- GET  /storage/usage             data-dir footprint + drive health
- POST /storage/check              pre-ingest path + free-space probe
- POST /storage/relocate           start a verified data-dir move
- GET  /storage/relocate/{job_id}  poll relocation progress

all endpoints require an authenticated user. the relocate endpoints
are lite-only (server profile uses minio + external disk management)
and admin-only. see issue #47.
"""

import mimetypes
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.config import get_settings
from loom.dependencies import get_db_session, get_storage_backend
from loom.models.asset import Asset
from loom.schemas.storage import (
    RelocationJobStatus,
    RelocationRequest,
    RelocationStartResponse,
    StorageCheckRequest,
    StorageCheckResponse,
    StorageUsage,
)
from loom.security.rate_limit import limiter
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.storage_backends import (
    DERIVATIVES_BUCKET,
    ORIGINALS_BUCKET,
    StorageBackend,
)
from loom.services.storage_backends.local import LocalStorageBackend
from loom.services.storage_relocation import (
    RELOCATION_REGISTRY,
    compute_advisory,
    get_storage_usage,
    probe_path_writable,
    start_relocation,
)

router = APIRouter(prefix="/storage", tags=["storage"])

_SERVABLE_BUCKETS = frozenset({ORIGINALS_BUCKET, DERIVATIVES_BUCKET})


def _require_lite() -> None:
    """reject calls on the server profile.

    returns 404 rather than 403 so probing the endpoint can't be
    used to confirm a server-profile deploy is running.
    """
    settings = get_settings()
    if not settings.is_lite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=("storage relocation is only available on Lite profile"),
        )


@router.get("/usage", response_model=StorageUsage)
async def storage_usage(
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> StorageUsage:
    _require_lite()
    del token_payload  # auth gate only; no per-user filtering.
    db: AsyncSession = session  # type: ignore[assignment]
    settings = get_settings()
    data_dir = settings.resolved_data_dir()

    usage = get_storage_usage(data_dir)
    result = await db.execute(select(func.count()).select_from(Asset))
    asset_count = int(result.scalar_one())

    return StorageUsage(
        data_dir=str(usage["data_dir"]),
        free_bytes=int(usage["free_bytes"]),
        total_bytes=int(usage["total_bytes"]),
        originals_bytes=int(usage["originals_bytes"]),
        derivatives_bytes=int(usage["derivatives_bytes"]),
        db_bytes=int(usage["db_bytes"]),
        logs_bytes=int(usage["logs_bytes"]),
        asset_count=asset_count,
        on_system_drive=bool(usage["on_system_drive"]),
    )


@router.post("/check", response_model=StorageCheckResponse)
async def storage_check(
    body: StorageCheckRequest,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> StorageCheckResponse:
    """evaluate whether ``path`` can safely host a given batch.

    callable on both profiles: the frontend reuses this endpoint as
    a pre-flight check on server deploys too (there the advisory is
    informational because minio handles actual placement).
    """
    del token_payload
    path = Path(body.path)
    writable, reason = probe_path_writable(path)
    if not writable:
        # we still return disk_usage when possible so the UI can
        # explain *why* the path is bad ("no space" vs "wrong type").
        free_bytes = 0
        total_bytes = 0
        try:
            probe = path.expanduser().resolve()
            if probe.exists() or probe.parent.exists():
                usage = shutil.disk_usage(
                    probe if probe.exists() else probe.parent
                )
                free_bytes = int(usage.free)
                total_bytes = int(usage.total)
        except OSError:
            pass
        return StorageCheckResponse(
            writable=False,
            writable_reason=reason,
            free_bytes=free_bytes,
            total_bytes=total_bytes,
            on_system_drive=False,
            advisory="blocked",
            advisory_reason=reason,
        )

    usage_info = get_storage_usage(path)
    free_bytes = int(usage_info["free_bytes"])
    total_bytes = int(usage_info["total_bytes"])
    on_system_drive = bool(usage_info["on_system_drive"])
    advisory, advisory_reason = compute_advisory(
        free_bytes,
        total_bytes,
        body.estimated_batch_size,
        on_system_drive,
    )
    return StorageCheckResponse(
        writable=True,
        writable_reason=None,
        free_bytes=free_bytes,
        total_bytes=total_bytes,
        on_system_drive=on_system_drive,
        advisory=advisory,
        advisory_reason=advisory_reason,
    )


@router.post(
    "/relocate",
    response_model=RelocationStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("2/minute")
async def relocate(
    body: RelocationRequest,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> RelocationStartResponse:
    _require_lite()
    if token_payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required for data-dir relocation",
        )

    settings = get_settings()
    src = settings.resolved_data_dir()
    dst = Path(body.target_path)
    user_id = UUID(get_current_user_id(token_payload))
    session_factory = request.app.state.db_session_factory

    try:
        job = start_relocation(session_factory, src, dst, user_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    return RelocationStartResponse(job_id=job.job_id)


@router.get(
    "/relocate/{job_id}",
    response_model=RelocationJobStatus,
)
async def relocate_status(
    job_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
) -> RelocationJobStatus:
    _require_lite()
    del token_payload
    job = RELOCATION_REGISTRY.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"relocation job {job_id} not found",
        )
    return RelocationJobStatus(
        job_id=job.job_id,
        status=job.status,
        assets_copied=job.assets_copied,
        assets_total=job.assets_total,
        bytes_copied=job.bytes_copied,
        bytes_total=job.bytes_total,
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """parse a single byte range header.

    returns inclusive (start, end), or None to serve the whole object
    (header absent, malformed, or unsatisfiable — players tolerate a
    200 in that case).
    """
    if not header or not header.startswith("bytes=") or size == 0:
        return None
    spec = header[len("bytes=") :].split(",", 1)[0].strip()
    start_s, sep, end_s = spec.partition("-")
    if not sep:
        return None
    try:
        if start_s == "":
            suffix = int(end_s)
            if suffix <= 0:
                return None
            start, end = max(0, size - suffix), size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    end = min(end, size - 1)
    if start > end or start >= size:
        return None
    return start, end


@router.get("/object/{bucket}/{key:path}")
async def stream_object(
    bucket: str,
    key: str,
    request: Request,
    expires: int,
    method: str = "GET",
    sig: str = "",
    disposition: str = "inline",
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> StreamingResponse:
    """stream an asset's bytes for a signed url (lite profile).

    auth is the HMAC signature in the query string, not a bearer
    token — media elements (`<video>`, `<img>`, `<object>`) cannot
    send headers. supports HTTP Range so video seeking works. the
    server profile returns minio https urls directly and never hits
    this route (404 there).
    """
    _require_lite()
    if not isinstance(storage, LocalStorageBackend):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if bucket not in _SERVABLE_BUCKETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if method != "GET" or not storage.verify_signature(
        bucket, key, method, expires, sig
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid or expired signature",
        )

    try:
        size = storage.get_object_size(bucket, key)
    except (FileNotFoundError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="object not found",
        ) from err

    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    headers = {"Accept-Ranges": "bytes"}
    if disposition == "attachment":
        filename = key.rsplit("/", 1)[-1]
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    byte_range = _parse_range(request.headers.get("range", ""), size)
    if byte_range is not None:
        start, end = byte_range
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        return StreamingResponse(
            storage.get_object_range(bucket, key, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=content_type,
            headers=headers,
        )

    headers["Content-Length"] = str(size)
    _, stream = storage.get_object_stream(bucket, key)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers=headers,
    )
