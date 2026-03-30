import ipaddress
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

PLUGIN_TYPES = ("webhook", "activity", "integration")

WEBHOOK_EVENT_TYPES = (
    "asset.uploaded",
    "asset.processed",
    "asset.deleted",
    "annotation.created",
    "annotation.updated",
    "annotation.deleted",
    "event.created",
    "event.updated",
    "event.accepted",
    "export.completed",
    "case.created",
    "case.archived",
)


class PluginCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    version: str = Field(min_length=1, max_length=50)
    plugin_type: str
    config: dict[str, Any] | None = None

    @field_validator("plugin_type")
    @classmethod
    def validate_plugin_type(cls, v: str) -> str:
        if v not in PLUGIN_TYPES:
            raise ValueError(
                f"plugin_type must be one of: {', '.join(PLUGIN_TYPES)}"
            )
        return v


class PluginUpdate(BaseModel):
    description: str | None = None
    version: str | None = None
    is_enabled: bool | None = None
    config: dict[str, Any] | None = None


class PluginResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    version: str
    plugin_type: str
    is_enabled: bool
    config: dict[str, Any] | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PluginListResponse(BaseModel):
    items: list[PluginResponse]
    total: int


class WebhookCreate(BaseModel):
    plugin_id: UUID
    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(min_length=1)
    secret: str | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """reject non-http(s) schemes and private IP ranges."""
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Webhook URL must use http or https scheme")
        hostname = parsed.hostname
        if not hostname:
            raise ValueError("Webhook URL must include a hostname")
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or 443)
        except socket.gaierror as exc:
            raise ValueError(f"Could not resolve hostname: {hostname}") from exc
        for info in addr_infos:
            addr = ipaddress.ip_address(info[4][0])
            for network in _BLOCKED_NETWORKS:
                if addr in network:
                    raise ValueError(
                        f"Webhook URL resolves to private/reserved "
                        f"address {addr}"
                    )
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        invalid = [e for e in v if e not in WEBHOOK_EVENT_TYPES]
        if invalid:
            raise ValueError(
                f"invalid event types: {', '.join(invalid)}. "
                f"valid types: {', '.join(WEBHOOK_EVENT_TYPES)}"
            )
        return v


class WebhookUpdate(BaseModel):
    url: str | None = None
    events: list[str] | None = None
    is_active: bool | None = None

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = [e for e in v if e not in WEBHOOK_EVENT_TYPES]
            if invalid:
                raise ValueError(f"invalid event types: {', '.join(invalid)}")
        return v


class WebhookResponse(BaseModel):
    id: UUID
    plugin_id: UUID
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: datetime | None
    failure_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    items: list[WebhookResponse]
    total: int


class WebhookDeliveryResponse(BaseModel):
    id: UUID
    event_type: str
    status_code: int | None
    delivered_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryListResponse(BaseModel):
    items: list[WebhookDeliveryResponse]
    total: int
