from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import Uuid, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)
from sqlalchemy.types import TypeDecorator
from uuid_extensions import uuid7


def _generate_uuid7() -> UUID:
    """generate a uuid7 value for primary keys."""
    return UUID(str(uuid7()))


class _CoercibleUUID(TypeDecorator[UUID]):
    """UUID column that also accepts a ``str`` on bind.

    the stock SQLAlchemy ``Uuid`` bind processor calls ``value.hex`` and
    rejects plain strings under the sqlite (lite-profile) driver. user
    ids reach the query layer as strings -- the JWT ``sub`` claim via
    ``get_current_user_id`` and uuid path parameters -- so every
    ``where(User.id == sub)`` / ``where(Case.id == case_id)`` lookup
    raised ``'str' object has no attribute 'hex'`` under lite. coercing
    str -> UUID on bind fixes the whole class in one place; postgres
    (native uuid, server profile) is unaffected since a UUID passes
    through unchanged.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if isinstance(value, str):
            return UUID(value)
        return value


class Base(DeclarativeBase):
    # map every ``Mapped[UUID]`` column (primary keys and foreign keys)
    # onto the str-coercing uuid type above.
    type_annotation_map: ClassVar[dict[Any, Any]] = {UUID: _CoercibleUUID}


class UUIDMixin:
    """adds a uuid7 primary key column."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=_generate_uuid7,
    )


class TimestampMixin:
    """adds created_at and updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )
