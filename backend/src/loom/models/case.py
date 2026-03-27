from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Case(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'closed', 'archived')",
            name="ck_cases_status",
        ),
    )

    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="active",
    )
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )


class CaseMembership(UUIDMixin, Base):
    __tablename__ = "case_memberships"
    __table_args__ = (UniqueConstraint("case_id", "user_id"),)

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="viewer",
    )
    granted_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
