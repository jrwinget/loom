from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class FirstRunStatus(BaseModel):
    """status of first-run onboarding for the current deploy."""

    first_run_required: bool
    deployment_profile: Literal["server", "lite"]
    # resolved absolute path on lite profile; null on server.
    data_dir: str | None = None


class FirstRunCompleteRequest(BaseModel):
    """payload for bootstrapping the first admin user."""

    admin_email: EmailStr
    admin_password: str = Field(min_length=12)
    admin_full_name: str = Field(min_length=1, max_length=120)


class FirstRunCompleteResponse(BaseModel):
    """tokens + user id issued after first-run bootstrap."""

    user_id: UUID
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
