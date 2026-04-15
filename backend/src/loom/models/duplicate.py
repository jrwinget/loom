from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class DuplicateCluster(UUIDMixin, TimestampMixin, Base):
    """group of assets detected as duplicates or near-duplicates."""

    __tablename__ = "duplicate_clusters"

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="pending",
    )


class DuplicateClusterMember(UUIDMixin, Base):
    """individual asset membership in a duplicate cluster."""

    __tablename__ = "duplicate_cluster_members"
    __table_args__ = (
        UniqueConstraint(
            "cluster_id",
            "asset_id",
            name="uq_cluster_asset",
        ),
    )

    cluster_id: Mapped[UUID] = mapped_column(
        ForeignKey("duplicate_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phash: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    distance: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
