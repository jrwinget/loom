from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CaseCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class CaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class CasePurgeRequest(BaseModel):
    # exact case title, retyped to confirm intent; matched in the
    # handler against the loaded case
    confirm_title: str
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason must not be blank")
        return v


class CaseHoldRequest(BaseModel):
    # required for release too: the reason is recorded in the audit
    # trail even when it is not stored on the case
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason must not be blank")
        return stripped


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
    # no defaults: every constructor site must state the hold fields
    # explicitly so a missed site fails loudly instead of reporting
    # "not held" for a held case
    hold_active: bool
    hold_reason: str | None
    hold_set_by: UUID | None
    hold_set_at: datetime | None

    model_config = {"from_attributes": True}


class CaseListResponse(BaseModel):
    items: list[CaseResponse]
    total: int


class CaseMemberCreate(BaseModel):
    user_id: str
    role: str = "viewer"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"viewer", "editor", "owner"}
        if v not in allowed:
            raise ValueError(
                f"role must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class CaseMemberResponse(BaseModel):
    id: UUID
    case_id: UUID
    user_id: UUID
    user_email: str
    role: str
    granted_at: datetime

    model_config = {"from_attributes": True}
