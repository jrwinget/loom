from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class Derivative(UUIDMixin, Base):
    __tablename__ = "derivatives"

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
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
    )
    generation_params: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
