from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index(
            "ix_assets_case_upload_status",
            "case_id",
            "upload_status",
        ),
        CheckConstraint(
            "upload_status IN ("
            "'pending', 'uploading', 'complete', 'failed'"
            ")",
            name="ck_assets_upload_status",
        ),
        CheckConstraint(
            "processing_status IN ("
            "'pending', 'processing', 'complete', 'failed'"
            ")",
            name="ck_assets_processing_status",
        ),
    )

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
    )
    media_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    sha512_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    upload_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
    metadata_raw: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    metadata_extracted: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    capture_time: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )
    capture_location_lat: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    capture_location_lon: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    processing_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )
