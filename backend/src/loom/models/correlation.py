from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# JSONB on postgres for indexable structured payloads, JSON on sqlite
# (lite profile). the orm hides the type difference from query code;
# only ``->`` / ``@>`` operator usage would need to branch, and the
# reasoning column is only read whole.
_JSON_TYPE = JSONB().with_variant(JSON(), "sqlite")

from loom.models.base import Base, TimestampMixin, UUIDMixin


class CorrelationCandidate(UUIDMixin, TimestampMixin, Base):
    """a proposed grouping of assets covering the same event window.

    confidence in [0.0, 1.0] is the fused score across available
    signals (timestamp, geolocation, audio, visual). reasoning is a
    structured json record of which signals agreed vs disagreed so a
    reviewer can audit the call without re-running extraction.

    status transitions: pending -> accepted | rejected. no auto-merge.
    """

    __tablename__ = "correlation_candidates"
    __table_args__ = (
        Index(
            "ix_correlation_candidates_case_status",
            "case_id",
            "status",
        ),
        Index(
            "ix_correlation_candidates_case_window",
            "case_id",
            "start_utc",
            "end_utc",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_correlation_candidates_status",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_correlation_candidates_confidence_range",
        ),
        CheckConstraint(
            "end_utc >= start_utc",
            name="ck_correlation_candidates_window_order",
        ),
    )

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    reasoning: Mapped[dict[str, Any]] = mapped_column(
        _JSON_TYPE,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        default=None,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class CorrelationCandidateMember(UUIDMixin, Base):
    """membership of a single asset in a correlation candidate."""

    __tablename__ = "correlation_candidate_members"
    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            "asset_id",
            name="uq_correlation_candidate_asset",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "correlation_candidates.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
