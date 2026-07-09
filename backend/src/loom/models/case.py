from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
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
        # a unique index (not a table constraint) so the lite upgrade
        # can add it without a sqlite table rebuild
        Index(
            "ix_cases_source_bundle_sha256",
            "source_bundle_sha256",
            unique=True,
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
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # sha256 of the portable bundle this case was imported from, if
    # any. unique so re-importing the same bundle is rejected rather
    # than silently duplicating a whole case.
    source_bundle_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
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
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
