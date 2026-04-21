from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class Scene(UUIDMixin, Base):
    """a detected scene boundary within a video asset."""

    __tablename__ = "scenes"

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scene_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    start_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    end_time: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    start_frame: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    end_frame: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    thumbnail_key: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    duration: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
