from collections.abc import AsyncIterator
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from loom.dependencies import get_db_session
from loom.schemas.cluster import (
    AcceptClusterRequest,
    ClusterItemResponse,
    ClusterListResponse,
    EventClusterResponse,
    MergeClustersRequest,
    ProposeClusterRequest,
    SplitClusterRequest,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.clustering import (
    accept_cluster,
    get_cluster,
    list_clusters,
    merge_clusters,
    propose_clusters,
    reject_cluster,
    split_cluster,
)

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["clusters"],
)


def _cluster_response(cluster: Any) -> EventClusterResponse:
    """build response from cluster model."""
    items = getattr(cluster, "items", []) or []
    return EventClusterResponse(
        id=cluster.id,
        case_id=cluster.case_id,
        status=cluster.status,
        proposed_title=cluster.proposed_title,
        proposed_description=cluster.proposed_description,
        time_window_start=cluster.time_window_start,
        time_window_end=cluster.time_window_end,
        event_id=cluster.event_id,
        items=[
            ClusterItemResponse(
                id=item.id,
                asset_id=item.asset_id,
                content_type=item.content_type,
                content_id=item.content_id,
                absolute_time_start=item.absolute_time_start,
                absolute_time_end=item.absolute_time_end,
                text_preview=item.text_preview,
            )
            for item in items
        ],
        created_at=cluster.created_at,
    )


@router.post(
    "/clusters/propose",
    response_model=list[EventClusterResponse],
    status_code=status.HTTP_201_CREATED,
)
async def propose_clusters_endpoint(
    case_id: str,
    body: ProposeClusterRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> list[EventClusterResponse]:
    """trigger cross-source clustering (editor+)."""
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

    clusters = await propose_clusters(db, case_id, body.window_seconds, user_id)
    return [_cluster_response(c) for c in clusters]


@router.get(
    "/clusters",
    response_model=ClusterListResponse,
)
async def list_clusters_endpoint(
    case_id: str,
    cluster_status: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> ClusterListResponse:
    """list clusters for a case (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    clusters, total = await list_clusters(
        db, case_id, cluster_status, skip, limit
    )
    return ClusterListResponse(
        items=[_cluster_response(c) for c in clusters],
        total=total,
    )


@router.get(
    "/clusters/{cluster_id}",
    response_model=EventClusterResponse,
)
async def get_cluster_endpoint(
    case_id: str,
    cluster_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EventClusterResponse:
    """get a single cluster (viewer+)."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    cluster = await get_cluster(db, cluster_id, case_id)
    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="cluster not found",
        )
    return _cluster_response(cluster)


@router.post(
    "/clusters/{cluster_id}/accept",
    response_model=EventClusterResponse,
)
async def accept_cluster_endpoint(
    case_id: str,
    cluster_id: str,
    body: AcceptClusterRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EventClusterResponse:
    """accept a cluster (editor+)."""
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

    cluster = await accept_cluster(
        db,
        cluster_id,
        case_id,
        body.title,
        body.description,
        user_id,
    )
    return _cluster_response(cluster)


@router.post(
    "/clusters/{cluster_id}/reject",
    response_model=EventClusterResponse,
)
async def reject_cluster_endpoint(
    case_id: str,
    cluster_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EventClusterResponse:
    """reject a cluster (editor+)."""
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

    cluster = await reject_cluster(db, cluster_id, case_id, user_id)
    return _cluster_response(cluster)


@router.post(
    "/clusters/merge",
    response_model=EventClusterResponse,
)
async def merge_clusters_endpoint(
    case_id: str,
    body: MergeClustersRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EventClusterResponse:
    """merge clusters (editor+)."""
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

    cluster = await merge_clusters(db, body.cluster_ids, case_id, user_id)
    return _cluster_response(cluster)


@router.post(
    "/clusters/{cluster_id}/split",
    response_model=EventClusterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def split_cluster_endpoint(
    case_id: str,
    cluster_id: str,
    body: SplitClusterRequest,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EventClusterResponse:
    """split a cluster (editor+)."""
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

    cluster = await split_cluster(
        db, cluster_id, case_id, body.item_ids, user_id
    )
    return _cluster_response(cluster)
