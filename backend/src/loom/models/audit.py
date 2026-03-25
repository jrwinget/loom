from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class AuditLogEntry(UUIDMixin, Base):
    __tablename__ = "audit_log"

    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    resource_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )
    detail: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
