from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class CaseResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    status: str
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    asset_count: int = 0
    event_count: int = 0

    model_config = {"from_attributes": True}


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int


class CaseMemberCreate(BaseModel):
    user_id: str
    role: str = "viewer"


class CaseMemberResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    user_email: str
    role: str
    granted_at: datetime

    model_config = {"from_attributes": True}
