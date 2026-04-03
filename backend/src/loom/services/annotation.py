from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.user import User


async def create_annotation(
    session: AsyncSession,
    case_id: str,
    data: dict[str, Any],
    user_id: str,
) -> Annotation:
    """create an annotation on a case."""
    annotation = Annotation(
        case_id=UUID(case_id),
        asset_id=UUID(data["asset_id"]) if data.get("asset_id") else None,
        type=data["type"],
        content=data["content"],
        time_start=data.get("time_start"),
        time_end=data.get("time_end"),
        frame_number=data.get("frame_number"),
        spatial_region=data.get("spatial_region"),
        created_by=UUID(user_id),
    )
    session.add(annotation)
    await session.commit()
    await session.refresh(annotation)
    return annotation


async def list_annotations(
    session: AsyncSession,
    case_id: str,
    asset_id: str | None = None,
    annotation_type: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Annotation], int]:
    """list annotations for a case, with optional filters."""
    query = (
        select(Annotation, User.email)
        .join(User, User.id == Annotation.created_by)
        .where(Annotation.case_id == UUID(case_id))
        .where(Annotation.deleted_at.is_(None))
    )

    if asset_id is not None:
        query = query.where(Annotation.asset_id == UUID(asset_id))
    if annotation_type is not None:
        query = query.where(Annotation.type == annotation_type)

    # total count
    count_query = select(func.count()).select_from(
        query.with_only_columns(Annotation.id).subquery()
    )
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # paginated results
    query = query.order_by(Annotation.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    annotations = []
    for row in rows:
        annotation = row[0]
        annotation.created_by_email = row[1]
        annotations.append(annotation)

    return annotations, total


async def get_annotation(
    session: AsyncSession,
    annotation_id: str,
) -> Annotation | None:
    """get a single annotation by id (excludes soft-deleted)."""
    result = await session.execute(
        select(Annotation, User.email)
        .join(User, User.id == Annotation.created_by)
        .where(Annotation.id == UUID(annotation_id))
        .where(Annotation.deleted_at.is_(None))
    )
    row = result.one_or_none()
    if row is None:
        return None
    annotation = row[0]
    annotation.created_by_email = row[1]
    return annotation  # type: ignore[no-any-return]


async def update_annotation(
    session: AsyncSession,
    annotation_id: str,
    data: dict[str, Any],
) -> Annotation:
    """update annotation fields."""
    result = await session.execute(
        select(Annotation, User.email)
        .join(User, User.id == Annotation.created_by)
        .where(Annotation.id == UUID(annotation_id))
        .where(Annotation.deleted_at.is_(None))
    )
    row = result.one()
    annotation = row[0]
    email = row[1]

    for key, value in data.items():
        if value is not None:
            setattr(annotation, key, value)

    await session.commit()
    await session.refresh(annotation)

    annotation.created_by_email = email  # type: ignore[attr-defined]
    return annotation


async def delete_annotation(
    session: AsyncSession,
    annotation_id: str,
    user_id: str | None = None,
) -> bool:
    """soft-delete an annotation."""
    result = await session.execute(
        select(Annotation)
        .where(Annotation.id == UUID(annotation_id))
        .where(Annotation.deleted_at.is_(None))
    )
    annotation = result.scalar_one_or_none()
    if not annotation:
        return False

    annotation.deleted_at = datetime.now(UTC)
    if user_id:
        annotation.deleted_by = UUID(user_id)
    await session.commit()
    return True
