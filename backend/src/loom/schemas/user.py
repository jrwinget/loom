import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain a digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class MfaRequiredResponse(BaseModel):
    requires_mfa: bool = True
    challenge_token: str


class TokenRefresh(BaseModel):
    refresh_token: str
