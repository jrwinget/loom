from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Annotation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "annotations"
    __table_args__ = (
        Index("ix_annotations_case_asset", "case_id", "asset_id"),
        Index("ix_annotations_case_type", "case_id", "type"),
        Index(
            "ix_annotations_case_deleted_at",
            "case_id",
            "deleted_at",
        ),
    )

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"),
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None,
    )
    deleted_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        default=None,
    )
