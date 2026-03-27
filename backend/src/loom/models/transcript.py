from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class TranscriptSegment(UUIDMixin, Base):
    """immutable transcript segment tied to an asset."""

    __tablename__ = "transcript_segments"
    __table_args__ = (
        Index(
            "ix_transcript_segments_asset_start",
            "asset_id",
            "start_time",
        ),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    speaker_label: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    start_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    end_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    language: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
