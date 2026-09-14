from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin

NARRATIVE_STATUSES = ("draft", "approved", "rejected")


class NarrativeDraft(UUIDMixin, TimestampMixin, Base):
    """an ai-drafted prose narrative over a case's own structured
    metadata (chain-of-custody / audit-log entries) — never over
    evidentiary content such as transcripts, ocr text, or annotations.

    a dedicated table rather than reusing ``Annotation``: nothing in
    court_bundle.py/export.py picks this up until explicit, filtered
    inclusion code is written for it, so a draft can never leak into an
    export by riding along an existing, more permissive query. mirrors
    ``EventCluster``'s propose/review shape — ``status`` starts at
    ``"draft"`` and only a dedicated approve/reject endpoint may move it,
    never a generic update.
    """

    __tablename__ = "narrative_drafts"
    __table_args__ = (
        Index("ix_narrative_drafts_case_status", "case_id", "status"),
    )

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # set when the narrative is scoped to one asset's custody history
    # rather than the whole case.
    asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="draft",
    )
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    # ids of the ChainOfCustodyEntry/AuditLogEntry rows the narrative
    # was built from, for traceability back to the source-of-truth data.
    source_entry_ids: Mapped[Any] = mapped_column(
        JSON,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    model_params: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )
    generated_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # server-authoritative review state — set only by the approve/reject
    # endpoints, never accepted as client input on a generic update.
    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None,
    )
