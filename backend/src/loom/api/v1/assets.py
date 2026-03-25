import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session, get_minio_client
from loom.models.asset import Asset
from loom.schemas.asset import (
    AssetListResponse,
    AssetResponse,
    AssetUploadResponse,
    PresignedUrlRequest,
    PresignedUrlResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.hashing import compute_hashes_from_bytes
from loom.services.ingest import (
    create_asset_record,
    generate_storage_key,
    record_upload_custody,
    validate_file_type,
)
from loom.services.storage import (
    ORIGINALS_BUCKET,
    StorageService,
)

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
async def upload_asset(
    case_id: str,
    file: UploadFile,
    request: Request,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> AssetUploadResponse:
    """upload a file (<=100mb) to a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

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

    # create asset record first to get id
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

    # generate storage key and update asset
    storage_key = generate_storage_key(case_id, str(asset.id), filename)
    asset.storage_key = storage_key
    await db.flush()

    # upload to minio (sync call via executor)
    storage = StorageService(minio_client)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        storage.upload_bytes,
        ORIGINALS_BUCKET,
        storage_key,
        data,
        mime_type,
    )

    # record chain of custody
    ip_address = request.client.host if request.client else None
    await record_upload_custody(db, str(asset.id), user_id, ip_address)
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


@router.post(
    "/upload-url",
    response_model=PresignedUrlResponse,
)
async def get_upload_url(
    case_id: str,
    body: PresignedUrlRequest,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
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

    storage = StorageService(minio_client)
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
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> AssetUploadResponse:
    """finalize a presigned upload."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    storage = StorageService(minio_client)
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

    asset = await create_asset_record(
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
    )

    ip_address = request.client.host if request.client else None
    await record_upload_custody(db, str(asset.id), user_id, ip_address)
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
    storage: StorageService,
    bucket: str,
    prefix: str,
    minio_client: Minio,
) -> tuple[str, str] | None:
    """find the first object under a prefix."""
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
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AssetListResponse:
    """list assets for a case (paginated)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    # total count
    count_q = select(func.count(Asset.id)).where(Asset.case_id == UUID(case_id))
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # paginated query
    query = (
        select(Asset)
        .where(Asset.case_id == UUID(case_id))
        .offset(skip)
        .limit(limit)
        .order_by(Asset.created_at.desc())
    )
    result = await db.execute(query)
    assets = list(result.scalars().all())

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
    token_payload: dict = Depends(  # noqa: B008
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

    result = await db.execute(
        select(Asset).where(
            Asset.id == UUID(asset_id),
            Asset.case_id == UUID(case_id),
        )
    )
    asset = result.scalar_one_or_none()
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
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
    minio_client: Minio = Depends(  # noqa: B008
        get_minio_client
    ),
) -> PresignedUrlResponse:
    """get a presigned download url (15 min expiry)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    result = await db.execute(
        select(Asset).where(
            Asset.id == UUID(asset_id),
            Asset.case_id == UUID(case_id),
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="asset not found",
        )

    storage = StorageService(minio_client)
    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        storage.get_presigned_download_url,
        ORIGINALS_BUCKET,
        asset.storage_key,
        900,
    )

    return PresignedUrlResponse(url=url, key=asset.storage_key)
