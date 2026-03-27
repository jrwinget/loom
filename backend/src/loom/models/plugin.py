from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from loom.models.base import Base, TimestampMixin, UUIDMixin


class Plugin(UUIDMixin, TimestampMixin, Base):
    """installed plugin registration."""

    __tablename__ = "plugins"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    plugin_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    webhooks: Mapped[list["Webhook"]] = relationship(
        back_populates="plugin",
        cascade="all, delete-orphan",
    )


class Webhook(UUIDMixin, TimestampMixin, Base):
    """webhook subscription for a plugin."""

    __tablename__ = "webhooks"

    plugin_id: Mapped[UUID] = mapped_column(
        ForeignKey("plugins.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failure_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )

    plugin: Mapped["Plugin"] = relationship(
        back_populates="webhooks",
    )
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="webhook",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(UUIDMixin, Base):
    """immutable record of a webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"

    webhook_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhooks.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
    )

    webhook: Mapped["Webhook"] = relationship(
        back_populates="deliveries",
    )
