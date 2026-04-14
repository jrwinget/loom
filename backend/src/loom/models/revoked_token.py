from datetime import datetime
from uuid import UUID

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, UUIDMixin


class RevokedToken(UUIDMixin, Base):
    """tracks revoked jwt tokens by their jti claim."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        nullable=False,
        index=True,
    )
    revoked_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        nullable=False,
    )
