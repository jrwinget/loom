from pydantic import BaseModel


class MfaSetupResponse(BaseModel):
    provisioning_uri: str


class MfaVerifyRequest(BaseModel):
    code: str


class MfaVerifyResponse(BaseModel):
    recovery_codes: list[str]


class MfaChallengeRequest(BaseModel):
    challenge_token: str
    code: str


class MfaChallengeResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class MfaDisableRequest(BaseModel):
    code: str
