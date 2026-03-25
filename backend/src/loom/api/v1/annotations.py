from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.annotation import (
    AnnotationCreate,
    AnnotationListResponse,
    AnnotationResponse,
    AnnotationUpdate,
)
from loom.security.rbac import get_current_user_id, require_authenticated
from loom.services.annotation import (
    create_annotation,
    delete_annotation,
    get_annotation,
    list_annotations,
    update_annotation,
)
from loom.services.case import check_case_access

router = APIRouter(
    prefix="/cases/{case_id}/annotations",
    tags=["annotations"],
)


@router.post(
    "",
    response_model=AnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation_endpoint(
    case_id: str,
    body: AnnotationCreate,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AnnotationResponse:
    """create an annotation (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="editor"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    data = body.model_dump()
    annotation = await create_annotation(db, case_id, data, user_id)

    # fetch creator email
    from sqlalchemy import select

    from loom.models.user import User

    result = await db.execute(
        select(User.email).where(User.id == annotation.created_by)
    )
    email = result.scalar_one()

    return AnnotationResponse(
        id=annotation.id,
        case_id=annotation.case_id,
        asset_id=annotation.asset_id,
        type=annotation.type,
        content=annotation.content,
        time_start=annotation.time_start,
        time_end=annotation.time_end,
        frame_number=annotation.frame_number,
        spatial_region=annotation.spatial_region,
        created_by=annotation.created_by,
        created_by_email=email,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.get("", response_model=AnnotationListResponse)
async def list_annotations_endpoint(
    case_id: str,
    asset_id: str | None = Query(None),
    type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AnnotationListResponse:
    """list annotations for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    annotations, total = await list_annotations(
        db, case_id, asset_id, type, skip, limit
    )
    items = [
        AnnotationResponse(
            id=a.id,
            case_id=a.case_id,
            asset_id=a.asset_id,
            type=a.type,
            content=a.content,
            time_start=a.time_start,
            time_end=a.time_end,
            frame_number=a.frame_number,
            spatial_region=a.spatial_region,
            created_by=a.created_by,
            created_by_email=a.created_by_email,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in annotations
    ]
    return AnnotationListResponse(items=items, total=total)


@router.get(
    "/{annotation_id}",
    response_model=AnnotationResponse,
)
async def get_annotation_endpoint(
    case_id: str,
    annotation_id: str,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AnnotationResponse:
    """get a single annotation."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    annotation = await get_annotation(db, annotation_id)
    if not annotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="annotation not found",
        )

    return AnnotationResponse(
        id=annotation.id,
        case_id=annotation.case_id,
        asset_id=annotation.asset_id,
        type=annotation.type,
        content=annotation.content,
        time_start=annotation.time_start,
        time_end=annotation.time_end,
        frame_number=annotation.frame_number,
        spatial_region=annotation.spatial_region,
        created_by=annotation.created_by,
        created_by_email=annotation.created_by_email,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.patch(
    "/{annotation_id}",
    response_model=AnnotationResponse,
)
async def update_annotation_endpoint(
    case_id: str,
    annotation_id: str,
    body: AnnotationUpdate,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> AnnotationResponse:
    """update an annotation (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="editor"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    existing = await get_annotation(db, annotation_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="annotation not found",
        )

    data = body.model_dump(exclude_unset=True)
    annotation = await update_annotation(db, annotation_id, data)
    return AnnotationResponse(
        id=annotation.id,
        case_id=annotation.case_id,
        asset_id=annotation.asset_id,
        type=annotation.type,
        content=annotation.content,
        time_start=annotation.time_start,
        time_end=annotation.time_end,
        frame_number=annotation.frame_number,
        spatial_region=annotation.spatial_region,
        created_by=annotation.created_by,
        created_by_email=annotation.created_by_email,
        created_at=annotation.created_at,
        updated_at=annotation.updated_at,
    )


@router.delete(
    "/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_annotation_endpoint(
    case_id: str,
    annotation_id: str,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """delete an annotation (requires editor+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(
        db, case_id, user_id, required_role="editor"
    )
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    deleted = await delete_annotation(db, annotation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="annotation not found",
        )
