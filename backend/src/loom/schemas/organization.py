from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class OrgCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class OrgUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class OrgResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    member_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgListResponse(BaseModel):
    items: list[OrgResponse]
    total: int


class OrgMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    user_email: str
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class SharedEvidenceCreate(BaseModel):
    target_case_id: str
    asset_id: str
    access_level: str = "view"
    expires_at: datetime | None = None

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v: str) -> str:
        allowed = {"view", "annotate"}
        if v not in allowed:
            raise ValueError(
                f"access_level must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class SharedEvidenceResponse(BaseModel):
    id: UUID
    source_case_id: UUID
    target_case_id: UUID
    asset_id: UUID
    original_filename: str | None = None
    shared_by: UUID
    access_level: str
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
