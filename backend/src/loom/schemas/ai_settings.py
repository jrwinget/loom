from pydantic import BaseModel


class AiSettingsResponse(BaseModel):
    """ai engine config for the settings ui. the api key is never
    returned — only whether one is stored."""

    transcription_engine: str
    provider: str
    api_base_url: str
    transcription_model: str
    api_key_set: bool


class AiSettingsUpdate(BaseModel):
    """partial update; omitted fields are left unchanged. send an
    explicit value for ``api_key`` to set it."""

    transcription_engine: str | None = None
    provider: str | None = None
    api_base_url: str | None = None
    transcription_model: str | None = None
    api_key: str | None = None


class AiProviderModel(BaseModel):
    id: str
    label: str


class AiProvider(BaseModel):
    """a cloud transcription provider and its curated models, for the
    settings dropdowns. carries no secrets."""

    id: str
    label: str
    group: str
    models: list[AiProviderModel]
    requires_api_key: bool
    base_url: str
    base_url_editable: bool
    available: bool
    note: str


class AiProvidersResponse(BaseModel):
    providers: list[AiProvider]
