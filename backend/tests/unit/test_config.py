"""tests for secret key validation at startup."""

import pytest

from loom.config import Settings


def test_startup_rejects_default_secret() -> None:
    """app must reject the hardcoded default secret."""
    settings = Settings(
        secret_key="change-me-in-production",
    )
    with pytest.raises(ValueError, match="secret_key"):
        settings.validate_secret_key()


def test_startup_rejects_short_secret() -> None:
    """app must reject secret keys shorter than 32 characters."""
    settings = Settings(
        secret_key="too-short",
    )
    with pytest.raises(ValueError, match="32"):
        settings.validate_secret_key()


def test_startup_accepts_strong_secret() -> None:
    """a 32+ char random secret should be accepted."""
    settings = Settings(
        secret_key="a-sufficiently-long-secret-key-for-production-use",
    )
    # should not raise
    settings.validate_secret_key()
    assert len(settings.secret_key) >= 32
