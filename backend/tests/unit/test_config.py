"""tests for secret key validation at startup."""

import logging
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from loom.config import Settings, get_settings


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


class TestCorsOriginsValidation:
    """cors_origins must be well-formed absolute origins."""

    def test_accepts_https_origin(self) -> None:
        settings = Settings(cors_origins=["https://app.example.com"])
        assert settings.cors_origins == ["https://app.example.com"]

    def test_accepts_multiple_origins(self) -> None:
        settings = Settings(
            cors_origins=[
                "https://app.example.com",
                "http://localhost:3000",
            ],
        )
        assert settings.cors_origins == [
            "https://app.example.com",
            "http://localhost:3000",
        ]

    def test_strips_trailing_slash(self) -> None:
        """operators often paste URLs with a trailing slash."""
        settings = Settings(cors_origins=["https://app.example.com/"])
        assert settings.cors_origins == ["https://app.example.com"]

    def test_rejects_wildcard(self) -> None:
        with pytest.raises(ValidationError, match="'\\*'"):
            Settings(cors_origins=["*"])

    def test_rejects_empty_entry(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            Settings(cors_origins=["  "])

    def test_rejects_missing_scheme(self) -> None:
        with pytest.raises(ValidationError, match="absolute"):
            Settings(cors_origins=["app.example.com"])

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ValidationError, match="absolute"):
            Settings(cors_origins=["ftp://example.com"])

    def test_rejects_origin_with_path(self) -> None:
        with pytest.raises(ValidationError, match="path"):
            Settings(cors_origins=["https://example.com/app"])


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


class TestLifespanWiring:
    """``_lifespan`` must invoke every startup validator."""

    async def test_lifespan_rejects_lite_profile_with_postgres(self) -> None:
        """lite profile + postgres URL must abort startup."""
        bad = Settings(
            secret_key="a-sufficiently-long-secret-key-for-production-use",
            deployment_profile="lite",
            database_url="postgresql+asyncpg://x:y@h/db",
        )
        get_settings.cache_clear()

        # main.py does ``from loom.config import get_settings``, so the
        # patch target is the name as bound inside loom.main.
        with (
            patch("loom.main.get_settings", return_value=bad),
            patch("loom.config.get_settings", return_value=bad),
        ):
            from loom.main import _lifespan, create_app

            application = create_app()
            with pytest.raises(ValueError, match="sqlite"):
                async with _lifespan(application):
                    pass
