"""unit tests for the self-hosted transcription provider catalog."""

import pytest

from loom.services.ai_providers import (
    OPENAI_AUDIO,
    RETIRED_PROVIDER_IDS,
    get_provider,
    list_providers,
    requires_api_key,
    transport_for,
    validate_selection,
)


def test_catalog_has_the_expected_groups() -> None:
    ids = {p.id for p in list_providers()}
    assert ids == {"oss", "custom"}


def test_frontier_providers_are_gone() -> None:
    for retired in ("openai", "google", "anthropic"):
        assert get_provider(retired) is None


def test_transport_resolves_per_provider() -> None:
    assert transport_for("oss") == OPENAI_AUDIO
    assert transport_for("custom") == OPENAI_AUDIO
    # unknown/empty/retired ids fall back to the OpenAI-compatible path
    # (the id itself is still rejected as unknown by validate_selection)
    assert transport_for("") == OPENAI_AUDIO
    assert transport_for("nope") == OPENAI_AUDIO
    assert transport_for("openai") == OPENAI_AUDIO


def test_requires_api_key_defaults_true_for_unknown() -> None:
    assert requires_api_key("oss") is False
    assert requires_api_key("custom") is True
    assert requires_api_key("") is True
    # a retired id is "unknown" to the catalog now too
    assert requires_api_key("openai") is True


def test_validate_selection_accepts_free_form_for_custom() -> None:
    validate_selection("custom", "anything-goes")  # no raise


def test_validate_selection_accepts_catalog_model_for_oss() -> None:
    validate_selection("oss", "whisper-large-v3")  # no raise


@pytest.mark.parametrize(
    ("provider", "model", "match"),
    [
        ("nope", "x", "(?i)unknown ai provider"),
        ("openai", "gpt-4o-transcribe", "(?i)unknown ai provider"),
        ("google", "gemini-2.5-flash", "(?i)unknown ai provider"),
        ("anthropic", "claude", "(?i)unknown ai provider"),
        ("oss", "made-up-model", "(?i)model"),
        ("custom", "", "(?i)model"),
    ],
)
def test_validate_selection_rejects(
    provider: str, model: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_selection(provider, model)


def test_retired_provider_ids_are_not_in_the_catalog() -> None:
    live_ids = {p.id for p in list_providers()}
    assert live_ids.isdisjoint(RETIRED_PROVIDER_IDS)
