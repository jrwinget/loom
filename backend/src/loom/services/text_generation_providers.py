"""curated self-hosted text-generation providers and their models.

mirrors ai_providers.py's shape for a second capability (chat/completions
rather than audio transcription), but as its own module rather than a
shared dataclass: the two capabilities don't share a transport, a model
shape (a chat model has a context window; a transcription model doesn't),
or validation rules, so cramming them into one generic type would need
capability branching inside otherwise-shared functions.

only self-hosted/BYO-endpoint providers are offered: point loom at your
own OpenAI-compatible chat completions server (Ollama, vLLM, TGI, LM
Studio, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

# every self-hosted/custom chat server in common use (ollama, vllm, tgi,
# lm studio) speaks this wire protocol, so there is only one transport —
# unlike transcription, which had to dispatch between providers.
CHAT_COMPLETIONS = "chat_completions"


@dataclass(frozen=True)
class TextGenModel:
    id: str
    label: str
    context_window: int | None = None


@dataclass(frozen=True)
class TextGenProvider:
    id: str
    label: str
    group: str  # "oss" | "custom"
    transport: str
    base_url: str
    models: tuple[TextGenModel, ...]
    requires_api_key: bool = True
    base_url_editable: bool = False
    note: str = ""


_PROVIDERS: tuple[TextGenProvider, ...] = (
    TextGenProvider(
        id="oss",
        label="Open-source (self-hosted)",
        group="oss",
        transport=CHAT_COMPLETIONS,
        base_url="",
        base_url_editable=True,
        requires_api_key=False,
        models=(
            TextGenModel("gpt-oss-20b", "gpt-oss-20b", 128_000),
            TextGenModel("gpt-oss-120b", "gpt-oss-120b", 128_000),
            TextGenModel(
                "qwen2.5-32b-instruct", "Qwen2.5 32B Instruct", 128_000
            ),
            TextGenModel(
                "mistral-nemo-12b-instruct",
                "Mistral NeMo 12B Instruct",
                128_000,
            ),
        ),
        note=(
            "Point at your own OpenAI-compatible chat endpoint (Ollama, "
            "vLLM, TGI, LM Studio) running the selected model."
        ),
    ),
    TextGenProvider(
        id="custom",
        label="Custom (OpenAI-compatible)",
        group="custom",
        transport=CHAT_COMPLETIONS,
        base_url="",
        base_url_editable=True,
        models=(),
        note="Any OpenAI-compatible /chat/completions endpoint.",
    ),
)

_BY_ID = {p.id: p for p in _PROVIDERS}


def list_text_gen_providers() -> list[TextGenProvider]:
    return list(_PROVIDERS)


def get_text_gen_provider(provider_id: str) -> TextGenProvider | None:
    return _BY_ID.get(provider_id)


def requires_api_key(provider_id: str) -> bool:
    provider = _BY_ID.get(provider_id)
    # unknown/empty -> assume a hosted provider that needs a key.
    return provider.requires_api_key if provider else True


def validate_text_gen_selection(provider_id: str, model: str) -> None:
    """raise ValueError if (provider, model) isn't a valid text-gen choice."""
    provider = _BY_ID.get(provider_id)
    if provider is None:
        raise ValueError(f"unknown text-generation provider: {provider_id!r}")
    # providers with a curated catalog offer it as defaults but still
    # accept a free-form model id (self-hosted server model names churn
    # too fast to hard-gate on the curated list).
    if not model:
        raise ValueError("a text-generation model must be selected")
