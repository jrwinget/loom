from pydantic import BaseModel


class AiSettingsResponse(BaseModel):
    """ai engine config for the settings ui. the api key is never
    returned — only whether one is stored."""

    transcription_engine: str
    provider: str
    api_base_url: str
    transcription_model: str
    whisper_model: str
    api_key_set: bool
    # false when ``provider`` names a catalog entry that no longer
    # exists (e.g. a frontier provider that has since been removed) —
    # the ui shows a warning instead of silently disabling cloud
    # transcription with no explanation.
    provider_available: bool = True
    # false when a stored api key can't be decrypted with the currently
    # -available key (rotated/lost key, corrupt data, moved to a
    # different machine) — the ui prompts re-entry rather than letting
    # cloud transcription fail opaquely at inference time.
    key_decryptable: bool = True


class AiSettingsUpdate(BaseModel):
    """partial update; omitted fields are left unchanged. send an
    explicit value for ``api_key`` to set it."""

    transcription_engine: str | None = None
    provider: str | None = None
    api_base_url: str | None = None
    transcription_model: str | None = None
    api_key: str | None = None
    whisper_model: str | None = None


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


class TextGenProviderModel(BaseModel):
    id: str
    label: str
    context_window: int | None = None


class TextGenProvider(BaseModel):
    """a self-hosted/custom text-generation provider and its curated
    models, for the settings dropdowns. carries no secrets."""

    id: str
    label: str
    group: str
    models: list[TextGenProviderModel]
    requires_api_key: bool
    base_url: str
    base_url_editable: bool
    note: str


class TextGenProvidersResponse(BaseModel):
    providers: list[TextGenProvider]


class TextGenSettingsResponse(BaseModel):
    """text-generation config for the settings ui. the api key is never
    returned — only whether one is stored."""

    enabled: bool
    provider: str
    api_base_url: str
    model: str
    api_key_set: bool
    provider_available: bool = True
    key_decryptable: bool = True


class TextGenSettingsUpdate(BaseModel):
    """partial update; omitted fields are left unchanged. send an
    explicit value for ``api_key`` to set it."""

    enabled: bool | None = None
    provider: str | None = None
    api_base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
