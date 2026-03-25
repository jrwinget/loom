from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class TimelineEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "timeline_events"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    event_time_start: Mapped[datetime] = mapped_column(
        nullable=False,
    )
    event_time_end: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )
    time_precision: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="approximate",
    )
    location_description: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    location_lat: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    location_lon: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    location_confidence: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="unknown",
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="draft",
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )


class TimelineEventEvidence(UUIDMixin, Base):
    __tablename__ = "timeline_event_evidence"

    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("timeline_events.id"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id"),
        nullable=True,
    )
    annotation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("annotations.id"),
        nullable=True,
    )
    derivative_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("derivatives.id"),
        nullable=True,
    )
    clip_start: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    clip_end: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    relationship: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    linked_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    linked_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
