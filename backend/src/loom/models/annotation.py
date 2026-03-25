from typing import Any
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Annotation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "annotations"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    time_start: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    time_end: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    frame_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    spatial_region: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
