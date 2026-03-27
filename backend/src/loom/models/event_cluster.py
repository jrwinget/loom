from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class EventCluster(UUIDMixin, TimestampMixin, Base):
    """proposed cross-source event cluster."""

    __tablename__ = "event_clusters"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="proposed",
    )
    proposed_title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    proposed_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    time_window_start: Mapped[datetime] = mapped_column(
        nullable=False,
    )
    time_window_end: Mapped[datetime] = mapped_column(
        nullable=False,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("timeline_events.id"),
        nullable=True,
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )


class EventClusterItem(UUIDMixin, Base):
    """single content item within an event cluster."""

    __tablename__ = "event_cluster_items"

    cluster_id: Mapped[UUID] = mapped_column(
        ForeignKey("event_clusters.id"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    content_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    absolute_time_start: Mapped[datetime] = mapped_column(
        nullable=False,
    )
    absolute_time_end: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )
    text_preview: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
