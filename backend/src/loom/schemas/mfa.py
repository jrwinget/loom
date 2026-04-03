from pydantic import BaseModel, Field


class MfaSetupResponse(BaseModel):
    provisioning_uri: str
    mfa_enabled: bool = False


class MfaVerifyRequest(BaseModel):
    code: str = Field(
        min_length=6, max_length=6, pattern=r"^\d{6}$"
    )


class MfaVerifyResponse(BaseModel):
    mfa_enabled: bool = True
    recovery_codes: list[str]


class MfaChallengeRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=12)


class MfaChallengeResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class MfaDisableRequest(BaseModel):
    code: str = Field(
        min_length=6, max_length=6, pattern=r"^\d{6}$"
    )


class MfaLoginResponse(BaseModel):
    requires_mfa: bool = True
    challenge_token: str
