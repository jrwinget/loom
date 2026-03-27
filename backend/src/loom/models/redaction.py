from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Redaction(UUIDMixin, TimestampMixin, Base):
    """tracks redaction operations applied to asset derivatives.

    originals are never modified. each redaction produces a new
    derivative stored in minio under output_storage_key.
    """

    __tablename__ = "redactions"
    __table_args__ = (
        CheckConstraint(
            "redaction_type IN ('blur', 'black_box', 'pixelate', 'audio_mute')",
            name="ck_redactions_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'complete', 'failed')",
            name="ck_redactions_status",
        ),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redacted_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    redaction_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    regions: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )
    output_storage_key: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
