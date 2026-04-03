from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from loom.models.base import Base, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="analyst",
    )
    password_hash: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    mfa_secret: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        default=False,
    )
    recovery_codes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
    )
