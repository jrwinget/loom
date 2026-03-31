from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    password: str = Field(min_length=12)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """enforce nist 800-63b password complexity."""
        if not any(c.isupper() for c in v):
            raise ValueError(
                "password must contain at least one uppercase letter"
            )
        if not any(c.islower() for c in v):
            raise ValueError(
                "password must contain at least one lowercase letter"
            )
        if not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one digit")
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


class TokenRefresh(BaseModel):
    refresh_token: str
