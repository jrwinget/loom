from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class ExportBundle(UUIDMixin, Base):
    __tablename__ = "export_bundles"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    format: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    manifest: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
