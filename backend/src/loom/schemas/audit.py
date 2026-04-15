from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    id: UUID
    actor_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: UUID
    detail: Any | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditEntryListResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int


class AuditFilters(BaseModel):
    actor_id: UUID | None = None
    resource_type: str | None = None
    action: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ActionCount(BaseModel):
    action: str
    count: int


class ActorCount(BaseModel):
    actor_id: UUID
    count: int


class AuditStatsResponse(BaseModel):
    total_entries: int
    by_action: list[ActionCount]
    by_actor: list[ActorCount]
    earliest_entry: datetime | None = None
    latest_entry: datetime | None = None
