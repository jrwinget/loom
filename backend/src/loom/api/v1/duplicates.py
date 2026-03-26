from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.models.asset import Asset
from loom.models.duplicate import (
    DuplicateCluster,
    DuplicateClusterMember,
)
from loom.schemas.duplicate import (
    ClusterMemberResponse,
    ClusterUpdateRequest,
    DuplicateClusterResponse,
    DuplicateListResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.duplicate_detection import (
    create_cluster,
    find_duplicates,
    set_primary_member,
    update_cluster_status,
)

router = APIRouter(
    prefix="/cases/{case_id}/duplicates",
    tags=["duplicates"],
)


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


@router.get("", response_model=DuplicateListResponse)
async def list_duplicates(
    case_id: str,
    cluster_status: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> DuplicateListResponse:
    """list duplicate clusters for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id)

    # count query
    count_q = select(func.count(DuplicateCluster.id)).where(
        DuplicateCluster.case_id == UUID(case_id)
    )
    if cluster_status:
        count_q = count_q.where(DuplicateCluster.status == cluster_status)
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    # paginated clusters
    query = (
        select(DuplicateCluster)
        .where(DuplicateCluster.case_id == UUID(case_id))
        .offset(skip)
        .limit(limit)
        .order_by(DuplicateCluster.created_at.desc())
    )
    if cluster_status:
        query = query.where(DuplicateCluster.status == cluster_status)
    result = await db.execute(query)
    clusters = list(result.scalars().all())

    # load members for each cluster
    cluster_responses = []
    for cluster in clusters:
        members_result = await db.execute(
            select(DuplicateClusterMember, Asset.original_filename)
            .join(
                Asset,
                Asset.id == DuplicateClusterMember.asset_id,
            )
            .where(DuplicateClusterMember.cluster_id == cluster.id)
        )
        member_rows = members_result.all()
        members = [
            ClusterMemberResponse(
                id=m.id,
                asset_id=m.asset_id,
                original_filename=fname,
                phash=m.phash,
                distance=m.distance,
                is_primary=m.is_primary,
            )
            for m, fname in member_rows
        ]
        cluster_responses.append(
            DuplicateClusterResponse(
                id=cluster.id,
                case_id=cluster.case_id,
                status=cluster.status,
                members=members,
                created_at=cluster.created_at,
            )
        )

    return DuplicateListResponse(
        clusters=cluster_responses,
        total=total,
    )


@router.post(
    "/scan",
    response_model=DuplicateListResponse,
    status_code=status.HTTP_200_OK,
)
async def scan_duplicates(
    case_id: str,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> DuplicateListResponse:
    """scan for duplicate assets in a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    found = await find_duplicates(db, case_id)

    created_clusters = []
    for group in found:
        cluster = await create_cluster(
            db,
            case_id,
            group["asset_ids"],
            group["phashes"],
        )
        created_clusters.append(cluster)

    await db.commit()

    # build response
    cluster_responses = []
    for cluster in created_clusters:
        members_result = await db.execute(
            select(
                DuplicateClusterMember,
                Asset.original_filename,
            )
            .join(
                Asset,
                Asset.id == DuplicateClusterMember.asset_id,
            )
            .where(DuplicateClusterMember.cluster_id == cluster.id)
        )
        member_rows = members_result.all()
        members = [
            ClusterMemberResponse(
                id=m.id,
                asset_id=m.asset_id,
                original_filename=fname,
                phash=m.phash,
                distance=m.distance,
                is_primary=m.is_primary,
            )
            for m, fname in member_rows
        ]
        cluster_responses.append(
            DuplicateClusterResponse(
                id=cluster.id,
                case_id=cluster.case_id,
                status=cluster.status,
                members=members,
                created_at=cluster.created_at,
            )
        )

    return DuplicateListResponse(
        clusters=cluster_responses,
        total=len(cluster_responses),
    )


@router.patch(
    "/{cluster_id}",
    response_model=DuplicateClusterResponse,
)
async def update_cluster(
    case_id: str,
    cluster_id: str,
    body: ClusterUpdateRequest,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> DuplicateClusterResponse:
    """update cluster status or set primary member."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    # verify cluster belongs to case
    result = await db.execute(
        select(DuplicateCluster).where(
            DuplicateCluster.id == UUID(cluster_id),
            DuplicateCluster.case_id == UUID(case_id),
        )
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cluster not found",
        )

    if body.status:
        cluster = await update_cluster_status(db, cluster_id, body.status)

    if body.primary_asset_id:
        await set_primary_member(db, cluster_id, str(body.primary_asset_id))

    await db.commit()
    await db.refresh(cluster)

    # load members
    members_result = await db.execute(
        select(
            DuplicateClusterMember,
            Asset.original_filename,
        )
        .join(
            Asset,
            Asset.id == DuplicateClusterMember.asset_id,
        )
        .where(DuplicateClusterMember.cluster_id == cluster.id)
    )
    member_rows = members_result.all()
    members = [
        ClusterMemberResponse(
            id=m.id,
            asset_id=m.asset_id,
            original_filename=fname,
            phash=m.phash,
            distance=m.distance,
            is_primary=m.is_primary,
        )
        for m, fname in member_rows
    ]

    return DuplicateClusterResponse(
        id=cluster.id,
        case_id=cluster.case_id,
        status=cluster.status,
        members=members,
        created_at=cluster.created_at,
    )


@router.delete(
    "/{cluster_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def dismiss_cluster(
    case_id: str,
    cluster_id: str,
    token_payload: dict = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """dismiss a duplicate cluster."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)
    await _check_access(db, case_id, user_id, "editor")

    result = await db.execute(
        select(DuplicateCluster).where(
            DuplicateCluster.id == UUID(cluster_id),
            DuplicateCluster.case_id == UUID(case_id),
        )
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cluster not found",
        )

    cluster.status = "dismissed"
    await db.commit()
