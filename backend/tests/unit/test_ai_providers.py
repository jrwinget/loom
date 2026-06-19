"""unit tests for the cloud transcription provider catalog."""

import pytest

from loom.services.ai_providers import (
    GEMINI,
    OPENAI_AUDIO,
    get_provider,
    list_providers,
    requires_api_key,
    transport_for,
    validate_selection,
)


def test_catalog_has_the_expected_groups() -> None:
    ids = {p.id for p in list_providers()}
    assert {"openai", "google", "anthropic", "oss", "custom"} <= ids


def test_anthropic_is_listed_but_unavailable() -> None:
    anthropic = get_provider("anthropic")
    assert anthropic is not None
    assert anthropic.available is False
    assert anthropic.models == ()


def test_transport_resolves_per_provider() -> None:
    assert transport_for("google") == GEMINI
    assert transport_for("openai") == OPENAI_AUDIO
    # unknown/empty falls back to the OpenAI-compatible path
    assert transport_for("") == OPENAI_AUDIO
    assert transport_for("nope") == OPENAI_AUDIO


def test_requires_api_key_defaults_true_for_unknown() -> None:
    assert requires_api_key("openai") is True
    assert requires_api_key("oss") is False
    assert requires_api_key("") is True


def test_validate_selection_accepts_catalog_model() -> None:
    validate_selection("openai", "gpt-4o-transcribe")  # no raise


def test_validate_selection_accepts_free_form_for_custom() -> None:
    validate_selection("custom", "anything-goes")  # no raise


@pytest.mark.parametrize(
    ("provider", "model", "match"),
    [
        ("nope", "x", "(?i)provider"),
        ("anthropic", "x", "(?i)not available"),
        ("openai", "made-up", "(?i)model"),
        ("openai", "", "(?i)model"),
    ],
)
def test_validate_selection_rejects(
    provider: str, model: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_selection(provider, model)
