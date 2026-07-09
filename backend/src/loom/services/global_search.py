"""cross-case global search for the command palette.

the load-bearing invariant: a user only ever sees content from
cases they are a member of (admins see all). every subquery here is
constrained to the caller's member-case set, resolved once up front,
so there is a single place to audit the access boundary.

v1 is ilike over the obvious title/text columns. a tsvector/fts5
upgrade is a separate design note — virtual tables need
post-create_all ddl and a schema-parity allowlist.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from loom.models.annotation import Annotation
from loom.models.asset import Asset
from loom.models.case import Case, CaseMembership
from loom.models.timeline import TimelineEvent
from loom.models.user import User


def _ilike_pattern(query: str) -> str:
    escaped = (
        query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


async def _member_case_ids(
    session: AsyncSession, user_id: str
) -> list[UUID] | None:
    """the case-id set the caller may search, or None for 'all cases'.

    None is the admin signal — admins search every case, matching
    check_case_access's admin bypass. a non-admin with no
    memberships gets an empty list (searches nothing).
    """
    user = await session.get(User, UUID(user_id))
    if user is not None and user.role == "admin":
        return None
    rows = await session.scalars(
        select(CaseMembership.case_id).where(
            CaseMembership.user_id == UUID(user_id)
        )
    )
    return list(rows)


async def search_global(
    session: AsyncSession,
    user_id: str,
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """search across the caller's accessible cases, all content types.

    returns rows shaped ``{type, id, case_id, title, snippet}`` for
    the palette to render and route on.
    """
    text = query.strip()
    if not text:
        return []

    case_ids = await _member_case_ids(session, user_id)
    if case_ids is not None and not case_ids:
        # a non-admin who belongs to no case sees nothing — never a
        # broad query
        return []

    pattern = _ilike_pattern(text)
    subqueries = [
        _cases_q(pattern, case_ids),
        _assets_q(pattern, case_ids),
        _events_q(pattern, case_ids),
        _annotations_q(pattern, case_ids),
    ]
    combined = union_all(*subqueries).limit(limit)
    result = await session.execute(combined)
    return [
        {
            "type": row.type,
            # canonical hyphenated uuid strings, not the raw sqlite hex
            "id": str(row.id),
            "case_id": str(row.case_id),
            "title": row.title,
            "snippet": row.snippet,
        }
        for row in result
    ]


def _scope(column: Any, case_ids: list[UUID] | None) -> Any:
    """apply the member-case constraint unless the caller is admin."""
    if case_ids is None:
        return literal(True)
    return column.in_(case_ids)


def _cases_q(pattern: str, case_ids: list[UUID] | None) -> Any:
    return select(
        literal("case").label("type"),
        Case.id.label("id"),
        Case.id.label("case_id"),
        Case.name.label("title"),
        Case.description.label("snippet"),
    ).where(
        _scope(Case.id, case_ids),
        Case.name.ilike(pattern),
    )


def _assets_q(pattern: str, case_ids: list[UUID] | None) -> Any:
    return select(
        literal("asset").label("type"),
        Asset.id.label("id"),
        Asset.case_id.label("case_id"),
        Asset.original_filename.label("title"),
        literal(None).label("snippet"),
    ).where(
        _scope(Asset.case_id, case_ids),
        Asset.original_filename.ilike(pattern),
    )


def _events_q(pattern: str, case_ids: list[UUID] | None) -> Any:
    return select(
        literal("event").label("type"),
        TimelineEvent.id.label("id"),
        TimelineEvent.case_id.label("case_id"),
        TimelineEvent.title.label("title"),
        TimelineEvent.description.label("snippet"),
    ).where(
        _scope(TimelineEvent.case_id, case_ids),
        TimelineEvent.title.ilike(pattern)
        | TimelineEvent.description.ilike(pattern),
    )


def _annotations_q(pattern: str, case_ids: list[UUID] | None) -> Any:
    return select(
        literal("annotation").label("type"),
        Annotation.id.label("id"),
        Annotation.case_id.label("case_id"),
        Annotation.content.label("title"),
        literal(None).label("snippet"),
    ).where(
        _scope(Annotation.case_id, case_ids),
        Annotation.content.ilike(pattern),
    )
