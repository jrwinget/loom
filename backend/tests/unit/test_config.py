"""tests for secret key validation at startup."""

import logging

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


class TestCorsOriginsDefault:
    """cors_origins field defaults."""

    def test_cors_origins_default(self) -> None:
        """default cors_origins is localhost:3000."""
        settings = Settings()
        assert settings.cors_origins == ["http://localhost:3000"]


class TestValidateProductionSettings:
    """validate_production_settings warns on dev creds."""

    def test_validate_production_warns_on_default_db_creds(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """warn when default db url used in production."""
        settings = Settings(debug=False)
        with caplog.at_level(logging.WARNING):
            settings.validate_production_settings()
        assert any("database_url" in r.message for r in caplog.records)

    def test_validate_production_warns_on_default_minio_creds(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """warn when default minio creds used in production."""
        settings = Settings(
            debug=False,
            database_url=("postgresql+asyncpg://prod:prod@db:5432/loom"),
        )
        with caplog.at_level(logging.WARNING):
            settings.validate_production_settings()
        assert any("minio_access_key" in r.message for r in caplog.records)
        assert any("minio_secret_key" in r.message for r in caplog.records)

    def test_validate_production_silent_in_debug(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """no warnings when debug=True."""
        settings = Settings(debug=True)
        with caplog.at_level(logging.WARNING):
            settings.validate_production_settings()
        assert len(caplog.records) == 0
