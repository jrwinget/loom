from datetime import datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)
from uuid_extensions import uuid7


def _generate_uuid7() -> UUID:
    """generate a uuid7 value for primary keys."""
    return UUID(str(uuid7()))


class Base(DeclarativeBase):
    pass


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
