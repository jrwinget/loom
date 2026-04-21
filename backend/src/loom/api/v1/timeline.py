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
from loom.schemas.timeline import (
    EvidenceLinkCreate,
    EvidenceLinkResponse,
    TimelineEventCreate,
    TimelineEventDetailResponse,
    TimelineEventListResponse,
    TimelineEventResponse,
    TimelineEventUpdate,
    TimelineResponse,
)
from loom.security.rbac import (
    get_current_user_id,
    require_authenticated,
)
from loom.services.case import check_case_access
from loom.services.timeline import (
    create_event,
    get_event,
    get_timeline,
    link_evidence,
    list_events,
    unlink_evidence,
    update_event,
)

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["timeline"],
)


@router.post(
    "/events",
    response_model=TimelineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_endpoint(
    case_id: str,
    body: TimelineEventCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TimelineEventResponse:
    """create a timeline event (requires editor+)."""
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
    event = await create_event(db, case_id, data, user_id)
    return TimelineEventResponse(
        id=event.id,
        case_id=event.case_id,
        title=event.title,
        description=event.description,
        event_time_start=event.event_time_start,
        event_time_end=event.event_time_end,
        time_precision=event.time_precision,
        location_description=event.location_description,
        location_lat=event.location_lat,
        location_lon=event.location_lon,
        location_confidence=event.location_confidence,
        status=event.status,
        created_by=event.created_by,
        created_at=event.created_at,
        updated_at=event.updated_at,
        evidence_count=0,
        has_contradictions=False,
    )


@router.get(
    "/events",
    response_model=TimelineEventListResponse,
)
async def list_events_endpoint(
    case_id: str,
    event_status: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TimelineEventListResponse:
    """list events for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    events, total = await list_events(db, case_id, event_status, skip, limit)
    items = [
        TimelineEventResponse(
            id=e.id,
            case_id=e.case_id,
            title=e.title,
            description=e.description,
            event_time_start=e.event_time_start,
            event_time_end=e.event_time_end,
            time_precision=e.time_precision,
            location_description=(e.location_description),
            location_lat=e.location_lat,
            location_lon=e.location_lon,
            location_confidence=(e.location_confidence),
            status=e.status,
            created_by=e.created_by,
            created_at=e.created_at,
            updated_at=e.updated_at,
            evidence_count=getattr(e, "evidence_count", 0),
            has_contradictions=getattr(e, "has_contradictions", False),
        )
        for e in events
    ]
    return TimelineEventListResponse(items=items, total=total)


@router.get(
    "/events/{event_id}",
    response_model=TimelineEventResponse,
)
async def get_event_endpoint(
    case_id: str,
    event_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TimelineEventResponse:
    """get a single event."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    event = await get_event(db, event_id)
    if not event or str(event.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found",
        )

    return TimelineEventResponse(
        id=event.id,
        case_id=event.case_id,
        title=event.title,
        description=event.description,
        event_time_start=event.event_time_start,
        event_time_end=event.event_time_end,
        time_precision=event.time_precision,
        location_description=(event.location_description),
        location_lat=event.location_lat,
        location_lon=event.location_lon,
        location_confidence=(event.location_confidence),
        status=event.status,
        created_by=event.created_by,
        created_at=event.created_at,
        updated_at=event.updated_at,
        evidence_count=getattr(event, "evidence_count", 0),
        has_contradictions=getattr(event, "has_contradictions", False),
    )


@router.patch(
    "/events/{event_id}",
    response_model=TimelineEventResponse,
)
async def update_event_endpoint(
    case_id: str,
    event_id: str,
    body: TimelineEventUpdate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TimelineEventResponse:
    """update an event (requires editor+)."""
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

    existing = await get_event(db, event_id)
    if not existing or str(existing.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found",
        )

    data = body.model_dump(exclude_unset=True)
    event = await update_event(db, event_id, data)
    return TimelineEventResponse(
        id=event.id,
        case_id=event.case_id,
        title=event.title,
        description=event.description,
        event_time_start=event.event_time_start,
        event_time_end=event.event_time_end,
        time_precision=event.time_precision,
        location_description=(event.location_description),
        location_lat=event.location_lat,
        location_lon=event.location_lon,
        location_confidence=(event.location_confidence),
        status=event.status,
        created_by=event.created_by,
        created_at=event.created_at,
        updated_at=event.updated_at,
        evidence_count=getattr(event, "evidence_count", 0),
        has_contradictions=getattr(event, "has_contradictions", False),
    )


@router.post(
    "/events/{event_id}/evidence",
    response_model=EvidenceLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def link_evidence_endpoint(
    case_id: str,
    event_id: str,
    body: EvidenceLinkCreate,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> EvidenceLinkResponse:
    """link evidence to an event (requires editor+)."""
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

    existing = await get_event(db, event_id)
    if not existing or str(existing.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found",
        )

    data = body.model_dump()
    link = await link_evidence(db, event_id, data, user_id)
    return EvidenceLinkResponse(
        id=link.id,
        event_id=link.event_id,
        asset_id=link.asset_id,
        annotation_id=link.annotation_id,
        derivative_id=link.derivative_id,
        clip_start=link.clip_start,
        clip_end=link.clip_end,
        relationship=link.relationship,
        notes=link.notes,
        linked_by=link.linked_by,
        linked_at=link.linked_at,
    )


@router.delete(
    "/events/{event_id}/evidence/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_evidence_endpoint(
    case_id: str,
    event_id: str,
    link_id: str,
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> None:
    """unlink evidence from an event (editor+)."""
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

    # verify event belongs to this case before unlinking
    existing = await get_event(db, event_id)
    if not existing or str(existing.case_id) != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="event not found",
        )

    deleted = await unlink_evidence(db, link_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="evidence link not found",
        )


@router.get(
    "/timeline",
    response_model=TimelineResponse,
)
async def get_timeline_endpoint(
    case_id: str,
    event_status: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    token_payload: dict[str, Any] = Depends(  # noqa: B008
        require_authenticated
    ),
    session: AsyncIterator[AsyncSession] = Depends(  # noqa: B008
        get_db_session
    ),
) -> TimelineResponse:
    """get paginated timeline view for a case."""
    db: AsyncSession = session  # type: ignore[assignment]
    user_id = get_current_user_id(token_payload)

    has_access = await check_case_access(db, case_id, user_id)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient case access",
        )

    events = await get_timeline(
        db,
        case_id,
        status=event_status,
        skip=skip,
        limit=limit,
    )
    items = [
        TimelineEventDetailResponse(
            id=e.id,
            case_id=e.case_id,
            title=e.title,
            description=e.description,
            event_time_start=e.event_time_start,
            event_time_end=e.event_time_end,
            time_precision=e.time_precision,
            location_description=(e.location_description),
            location_lat=e.location_lat,
            location_lon=e.location_lon,
            location_confidence=(e.location_confidence),
            status=e.status,
            created_by=e.created_by,
            created_at=e.created_at,
            updated_at=e.updated_at,
            evidence_count=getattr(e, "evidence_count", 0),
            has_contradictions=getattr(e, "has_contradictions", False),
            evidence=[
                EvidenceLinkResponse(
                    id=ev.id,
                    event_id=ev.event_id,
                    asset_id=ev.asset_id,
                    annotation_id=ev.annotation_id,
                    derivative_id=ev.derivative_id,
                    clip_start=ev.clip_start,
                    clip_end=ev.clip_end,
                    relationship=ev.relationship,
                    notes=ev.notes,
                    linked_by=ev.linked_by,
                    linked_at=ev.linked_at,
                )
                for ev in getattr(e, "evidence", [])
            ],
        )
        for e in events
    ]
    return TimelineResponse(events=items)
