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
    mfa_enabled: bool
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


class PasswordRecoveryRequest(BaseModel):
    """payload for /auth/recover-password.

    `recovery_code` accepts either the hyphenated display form
    (``a1b2c-3d4e5-f6789-0abcd``) or the raw 20-hex-char form; the
    backend normalises before verifying.
    """

    email: EmailStr
    recovery_code: str = Field(min_length=20, max_length=64)
    new_password: str = Field(min_length=12)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        # mirror the rules enforced on /auth/register so a recovered
        # account never ends up holding a weaker credential than a
        # freshly registered one.
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain a digit")
        return v


class PasswordRecoveryResponse(BaseModel):
    """response from /auth/recover-password.

    `codes_remaining` lets the ui prompt the operator to mint fresh
    codes (or factory-reset) once they're running low. no tokens are
    issued here on purpose: after recovering, the user signs in
    normally so any active mfa enrollment still applies.
    """

    codes_remaining: int
