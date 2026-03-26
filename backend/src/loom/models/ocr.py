from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class OcrRegion(UUIDMixin, Base):
    """detected text region from ocr processing.

    immutable — no updated_at column.
    """

    __tablename__ = "ocr_regions"

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
        index=True,
    )
    frame_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    timestamp: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    bounding_box: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
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
