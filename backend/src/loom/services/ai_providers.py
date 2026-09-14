"""curated self-hosted cloud transcription providers and their models.

single source of truth for the provider/model dropdowns: the settings
ui fetches this via ``GET /settings/ai/providers`` and ``save_ai_config``
validates a (provider, model) pair against it. keeping the catalog here
— rather than duplicating it in the frontend — is what stops the two
from drifting. update model lists here when providers ship new ones.

only self-hosted/BYO-endpoint providers are offered: point loom at your
own OpenAI-compatible transcription server (vllm, whisper.cpp, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

# transports map a provider to the wire protocol used to call it.
# openai_audio -> POST {base}/audio/transcriptions (whisper-style)
OPENAI_AUDIO = "openai_audio"


@dataclass(frozen=True)
class ProviderModel:
    id: str
    label: str


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    group: str  # "oss" | "custom"
    transport: str
    base_url: str
    models: tuple[ProviderModel, ...]
    requires_api_key: bool = True
    # base_url is user-supplied (and validated) for self-hosted/custom
    # providers; for hosted providers it is derived from this catalog.
    base_url_editable: bool = False
    available: bool = True
    note: str = ""


_PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="oss",
        label="Open-source (self-hosted)",
        group="oss",
        transport=OPENAI_AUDIO,
        base_url="",
        base_url_editable=True,
        requires_api_key=False,
        models=(
            ProviderModel("whisper-large-v3", "Whisper large-v3"),
            ProviderModel("whisper-large-v3-turbo", "Whisper large-v3 turbo"),
            ProviderModel("distil-whisper-large-v3", "Distil-Whisper large-v3"),
        ),
        note=(
            "Point at your own OpenAI-compatible server (vLLM, "
            "whisper.cpp, etc.) running the selected model."
        ),
    ),
    Provider(
        id="custom",
        label="Custom (OpenAI-compatible)",
        group="custom",
        transport=OPENAI_AUDIO,
        base_url="",
        base_url_editable=True,
        models=(),
        note="Any OpenAI-compatible /audio/transcriptions endpoint.",
    ),
)

# providers that used to be offered and were withdrawn; a config saved
# while one of these was active must be actively reconciled (see
# ai_config.reconcile_retired_provider), never left to silently keep
# calling the real endpoint under a catalog entry that no longer exists.
RETIRED_PROVIDER_IDS = frozenset({"openai", "google", "anthropic"})

_BY_ID = {p.id: p for p in _PROVIDERS}


def list_providers() -> list[Provider]:
    return list(_PROVIDERS)


def get_provider(provider_id: str) -> Provider | None:
    return _BY_ID.get(provider_id)


def transport_for(provider_id: str) -> str:
    """resolve the wire protocol for a provider.

    an empty/unknown id (e.g. a config saved before providers existed)
    falls back to the OpenAI-compatible path, preserving old behavior.
    """
    provider = _BY_ID.get(provider_id)
    return provider.transport if provider else OPENAI_AUDIO


def requires_api_key(provider_id: str) -> bool:
    provider = _BY_ID.get(provider_id)
    # unknown/empty -> assume a hosted provider that needs a key.
    return provider.requires_api_key if provider else True


def validate_selection(provider_id: str, model: str) -> None:
    """raise ValueError if (provider, model) isn't a valid cloud choice."""
    provider = _BY_ID.get(provider_id)
    if provider is None:
        raise ValueError(f"unknown ai provider: {provider_id!r}")
    if not provider.available:
        raise ValueError(f"provider {provider.label} is not available")
    # providers with a fixed catalog must pick from it; custom (and any
    # provider with an open model list) accepts a free-form model id.
    allowed = {m.id for m in provider.models}
    if allowed and model not in allowed:
        raise ValueError(f"model {model!r} is not offered by {provider.label}")
    if not model:
        raise ValueError("a transcription model must be selected")
