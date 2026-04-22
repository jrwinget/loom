import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import (
    get_db_session,
    get_minio_client,
    get_storage_backend,
)
from loom.metrics import active_uploads
from loom.schemas.asset import (
    AssetListResponse,
    AssetResponse,
    AssetUploadResponse,
    ClockAnchorRequest,
    ClockAnchorResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
)
from loom.security.rate_limit import user_limiter
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
    require_role,
)
from loom.services.asset import get_asset as get_asset_svc
from loom.services.asset import list_assets as list_assets_svc
from loom.services.asset import restore_asset, soft_delete_asset
from loom.services.case import check_case_access
from loom.services.clock_drift import apply_clock_anchor
from loom.services.hashing import compute_hashes_from_bytes
from loom.services.ingest import (
    create_asset_record,
    create_asset_with_custody,
    generate_storage_key,
    record_upload_custody,
    validate_file_type,
)
from loom.services.storage_backends import ORIGINALS_BUCKET, StorageBackend

router = APIRouter(
    prefix="/cases/{case_id}/assets",
    tags=["assets"],
)

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100mb


async def _check_access(
    db: AsyncSession,
    case_id: str,
    user_id: str,
    required_role: str = "viewer",
) -> None:
    """verify user has case access or raise 403."""
    has_access = await check_case_access(
        db, case_id, user_id, required_role=required_role
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )


@router.post(
    "/upload",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@user_limiter.limit("10/minute")
async def upload_asset(
    case_id: str,
    file: UploadFile,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> AssetUploadResponse:
    """upload a file (<=100mb) to a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    active_uploads.inc()
    try:
        # read file bytes
        data = await file.read()
        if len(data) > _MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="file exceeds 100mb limit",
            )

        filename = file.filename or "unnamed"

        # validate file type by magic bytes
        try:
            mime_type, media_type = validate_file_type(data, filename)
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(err),
            ) from err

        # compute hashes
        sha256, sha512 = compute_hashes_from_bytes(data)

        # create asset + custody atomically in a savepoint
        ip_address = request.client.host if request.client else None

        async with db.begin_nested():
            asset = await create_asset_record(
                db,
                case_id,
                filename,
                "",  # placeholder key, updated below
                media_type,
                mime_type,
                len(data),
                sha256,
                sha512,
                user_id,
            )

            storage_key = generate_storage_key(
                case_id,
                str(asset.id),
                filename,
            )
            asset.storage_key = storage_key
            await db.flush()

            await record_upload_custody(
                db,
                str(asset.id),
                user_id,
                ip_address,
            )

        # upload via the shared storage backend (sync call via executor)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            storage.upload_bytes,
            ORIGINALS_BUCKET,
            storage_key,
            data,
            mime_type,
        )

        await db.commit()
        await db.refresh(asset)
    finally:
        active_uploads.dec()

    return AssetUploadResponse(
        id=asset.id,
        original_filename=asset.original_filename,
        media_type=asset.media_type,
        sha256_hash=asset.sha256_hash,
        upload_status=asset.upload_status,
        processing_status=asset.processing_status,
    )


@router.post(
    "/upload-url",
    response_model=PresignedUrlResponse,
)
@user_limiter.limit("10/minute")
async def get_upload_url(
    case_id: str,
    body: PresignedUrlRequest,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> PresignedUrlResponse:
    """get a presigned upload url for direct upload."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    # use a placeholder asset id for the key
    from uuid_extensions import uuid7

    placeholder_id = str(uuid7())
    storage_key = generate_storage_key(case_id, placeholder_id, body.filename)

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        storage.get_presigned_upload_url,
        ORIGINALS_BUCKET,
        storage_key,
    )

    return PresignedUrlResponse(url=url, key=storage_key)


@router.post(
    "/{asset_id}/complete",
    response_model=AssetUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_presigned_upload(
    case_id: str,
    asset_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> AssetUploadResponse:
    """finalize a presigned upload.

    ``minio_client`` is kept as a separate dep because the prefix
    scan (``list_objects``) is minio-specific; it has no
    equivalent on the lite-profile backend and is server-only.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    loop = asyncio.get_running_loop()

    # find files with this asset_id prefix
    prefix = f"{case_id}/{asset_id}/"
    exists = await loop.run_in_executor(
        None,
        _find_object_key,
        storage,
        ORIGINALS_BUCKET,
        prefix,
        minio_client,
    )

    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="uploaded file not found in storage",
        )

    storage_key, filename = exists

    # download and compute hashes
    import tempfile
    from pathlib import Path

    from loom.services.hashing import compute_hashes_from_file

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name

    await loop.run_in_executor(
        None,
        storage.download_file,
        ORIGINALS_BUCKET,
        storage_key,
        tmp_path,
    )

    path = Path(tmp_path)
    file_size = path.stat().st_size
    sha256, sha512 = compute_hashes_from_file(path)

    # read a small chunk for type detection
    data_head = path.read_bytes()[:8192]
    path.unlink()

    try:
        mime_type, media_type = validate_file_type(data_head, filename)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(err),
        ) from err

    ip_address = request.client.host if request.client else None
    asset = await create_asset_with_custody(
        db,
        case_id,
        filename,
        storage_key,
        media_type,
        mime_type,
        file_size,
        sha256,
        sha512,
        user_id,
        ip_address,
    )
    await db.commit()
    await db.refresh(asset)

    return AssetUploadResponse(
        id=asset.id,
        original_filename=asset.original_filename,
        media_type=asset.media_type,
        sha256_hash=asset.sha256_hash,
        upload_status=asset.upload_status,
        processing_status=asset.processing_status,
    )


def _find_object_key(
    storage: StorageBackend,
    bucket: str,
    prefix: str,
    minio_client: Minio,
) -> tuple[str, str] | None:
    """find the first object under a prefix (server-profile only)."""
    del storage  # unused; kept for callsite readability
    objects = minio_client.list_objects(bucket, prefix=prefix)
    for obj in objects:
        key = obj.object_name
        filename = key.rsplit("/", 1)[-1] if "/" in key else key
        return key, filename
    return None


@router.get("", response_model=AssetListResponse)
async def list_assets(
    case_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AssetListResponse:
    """list assets for a case (paginated).

    include_deleted is admin-only; non-admins always see
    only active assets.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    # only admins may see deleted assets
    role = token_payload.get("role", "")
    show_deleted = include_deleted and role == "admin"

    assets, total = await list_assets_svc(
        db,
        case_id,
        skip,
        limit,
        include_deleted=show_deleted,
    )

    return AssetListResponse(
        items=[AssetResponse.model_validate(a) for a in assets],
        total=total,
    )


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
)
async def get_asset(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AssetResponse:
    """get single asset detail."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    asset = await get_asset_svc(db, case_id, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    return AssetResponse.model_validate(asset)


@router.get(
    "/{asset_id}/download-url",
    response_model=PresignedUrlResponse,
)
async def get_download_url(
    case_id: str,
    asset_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    storage: StorageBackend = Depends(  # noqa: B008
        get_storage_backend
    ),
) -> PresignedUrlResponse:
    """get a presigned download url (15 min expiry)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    asset = await get_asset_svc(db, case_id, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        storage.get_presigned_download_url,
        ORIGINALS_BUCKET,
        asset.storage_key,
        900,
    )

    return PresignedUrlResponse(url=url, key=asset.storage_key)


@router.delete(
    "/{asset_id}",
    response_model=AssetResponse,
)
async def delete_asset(
    case_id: str,
    asset_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AssetResponse:
    """soft-delete an asset (editor+ required).

    marks the asset as deleted without removing any data.
    records a chain-of-custody entry for the deletion.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    # verify asset belongs to this case
    asset = await get_asset_svc(db, case_id, asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    ip_address = request.client.host if request.client else None
    try:
        asset = await soft_delete_asset(
            db,
            asset_id,
            user_id,
            ip_address,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err

    await db.commit()
    await db.refresh(asset)
    return AssetResponse.model_validate(asset)


@router.post(
    "/{asset_id}/clock-anchor",
    response_model=ClockAnchorResponse,
    status_code=status.HTTP_200_OK,
)
async def set_clock_anchor(
    case_id: str,
    asset_id: str,
    body: ClockAnchorRequest,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ClockAnchorResponse:
    """assert a clock correction for an asset (editor+).

    takes a (reported, actual) time pair, writes the offset onto
    the asset, and records an append-only chain-of-custody entry
    so the correction is defensible. clock_confidence is set to
    1.0 — a human claim is stronger than any automatic detection.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    asset = await get_asset_svc(db, case_id, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    ip_address = request.client.host if request.client else None
    try:
        updated = await apply_clock_anchor(
            db,
            asset_id,
            reported_time=body.reported_time,
            actual_time=body.actual_time,
            actor_id=user_id,
            note=body.note,
            ip_address=ip_address,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err

    await db.commit()
    await db.refresh(updated)
    return ClockAnchorResponse(
        asset_id=updated.id,
        clock_offset_seconds=updated.clock_offset_seconds or 0.0,
        clock_confidence=updated.clock_confidence or 0.0,
    )


@router.post(
    "/{asset_id}/restore",
    response_model=AssetResponse,
)
async def restore_asset_endpoint(
    case_id: str,
    asset_id: str,
    request: Request,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_role("admin")  # noqa: B008
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AssetResponse:
    """restore a soft-deleted asset (admin only).

    clears the deletion marker and records a custody entry.
    """
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    # verify asset belongs to this case (include deleted)
    asset = await get_asset_svc(
        db,
        case_id,
        asset_id,
        include_deleted=True,
    )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    ip_address = request.client.host if request.client else None
    try:
        asset = await restore_asset(
            db,
            asset_id,
            user_id,
            ip_address,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        ) from err

    await db.commit()
    await db.refresh(asset)
    return AssetResponse.model_validate(asset)
