from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models._append_only import enforce_append_only
from loom.models.base import Base, UUIDMixin


class AuditLogEntry(UUIDMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index(
            "ix_audit_log_created_actor",
            "timestamp",
            "actor_id",
        ),
        Index("ix_audit_log_resource_type", "resource_type"),
    )

    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
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


# append-only policy — any UPDATE or DELETE via the ORM is a bug
# at best and a tamper attempt at worst. server deploys also
# reject raw-SQL mutations via triggers installed in migration 011.
enforce_append_only(AuditLogEntry)
