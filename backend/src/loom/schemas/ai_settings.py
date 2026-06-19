from pydantic import BaseModel


class AiSettingsResponse(BaseModel):
    """ai engine config for the settings ui. the api key is never
    returned — only whether one is stored."""

    transcription_engine: str
    api_base_url: str
    transcription_model: str
    api_key_set: bool


class AiSettingsUpdate(BaseModel):
    """partial update; omitted fields are left unchanged. send an
    explicit value for ``api_key`` to set it."""

    transcription_engine: str | None = None
    api_base_url: str | None = None
    transcription_model: str | None = None
    api_key: str | None = None
