"""unit tests for the self-hosted text-generation provider catalog."""

import pytest

from loom.services.text_generation_providers import (
    CHAT_COMPLETIONS,
    get_text_gen_provider,
    list_text_gen_providers,
    requires_api_key,
    validate_text_gen_selection,
)


def test_catalog_has_the_expected_groups() -> None:
    ids = {p.id for p in list_text_gen_providers()}
    assert ids == {"oss", "custom"}


def test_no_frontier_provider_exists() -> None:
    for retired in ("openai", "google", "anthropic"):
        assert get_text_gen_provider(retired) is None


def test_transport_is_chat_completions_for_every_provider() -> None:
    for provider in list_text_gen_providers():
        assert provider.transport == CHAT_COMPLETIONS


def test_requires_api_key_defaults_true_for_unknown() -> None:
    assert requires_api_key("oss") is False
    assert requires_api_key("custom") is True
    assert requires_api_key("") is True
    assert requires_api_key("nope") is True


def test_oss_curated_models_carry_a_context_window() -> None:
    oss = get_text_gen_provider("oss")
    assert oss is not None
    assert len(oss.models) > 0
    for model in oss.models:
        assert model.context_window is not None


def test_validate_text_gen_selection_accepts_curated_model() -> None:
    validate_text_gen_selection("oss", "gpt-oss-20b")  # no raise


def test_validate_text_gen_selection_accepts_free_form_model() -> None:
    # unlike transcription, no provider hard-gates the model list — a
    # self-hosted server's model names churn too fast to allowlist.
    validate_text_gen_selection("oss", "some-brand-new-model")
    validate_text_gen_selection("custom", "anything-goes")


@pytest.mark.parametrize(
    ("provider", "model", "match"),
    [
        ("nope", "x", "(?i)unknown text-generation provider"),
        ("openai", "gpt-4o", "(?i)unknown text-generation provider"),
        ("oss", "", "(?i)model"),
        ("custom", "", "(?i)model"),
    ],
)
def test_validate_text_gen_selection_rejects(
    provider: str, model: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_text_gen_selection(provider, model)
