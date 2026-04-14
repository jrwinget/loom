from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class ProvenanceRecord(UUIDMixin, Base):
    __tablename__ = "provenance_records"

    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id"),
        nullable=True,
        index=True,
    )
    export_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("export_bundles.id"),
        nullable=True,
        index=True,
    )
    manifest_data: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    manifest_url: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    claim_generator: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    actions: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
