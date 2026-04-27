"""tests for secret key validation at startup."""

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
    """validate_production_settings fails fast on dev creds."""

    def test_rejects_default_db_creds(self) -> None:
        """default db url must abort startup."""
        settings = Settings(debug=False)
        with pytest.raises(ValueError, match="database_url"):
            settings.validate_production_settings()

    def test_rejects_default_minio_creds(self) -> None:
        """default minio creds must abort startup."""
        settings = Settings(
            debug=False,
            database_url=("postgresql+asyncpg://prod:prod@db:5432/loom"),
        )
        with pytest.raises(ValueError, match="minio_access_key"):
            settings.validate_production_settings()

    def test_lists_all_failures_in_one_error(self) -> None:
        """error message must enumerate every default in use."""
        settings = Settings(debug=False)
        with pytest.raises(ValueError) as exc_info:
            settings.validate_production_settings()
        message = str(exc_info.value)
        assert "database_url" in message
        assert "minio_access_key" in message
        assert "minio_secret_key" in message

    def test_accepts_production_credentials(self) -> None:
        """no error when every credential is non-default."""
        settings = Settings(
            debug=False,
            database_url="postgresql+asyncpg://prod:strong-pw@db:5432/loom",
            minio_access_key="prod-access-key",
            minio_secret_key="prod-secret-key",
        )
        # should not raise
        settings.validate_production_settings()

    def test_silent_in_debug(self) -> None:
        """debug mode bypasses all checks for dev convenience."""
        settings = Settings(debug=True)
        # should not raise even though every value is default
        settings.validate_production_settings()

    def test_silent_in_lite_profile(self) -> None:
        """lite profile uses sqlite + filesystem; checks don't apply."""
        settings = Settings(
            debug=False,
            deployment_profile="lite",
            database_url="sqlite+aiosqlite:///./loom.db",
            storage_signing_secret="x" * 32,
        )
        # should not raise even though minio creds are default
        settings.validate_production_settings()


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

    async def test_lifespan_rejects_default_minio_in_server_profile(
        self,
    ) -> None:
        """server profile + default minio creds must abort startup."""
        bad = Settings(
            secret_key="a-sufficiently-long-secret-key-for-production-use",
            deployment_profile="server",
            database_url="postgresql+asyncpg://prod:strong-pw@db:5432/loom",
            # minio_access_key + minio_secret_key default to dev values
        )
        get_settings.cache_clear()

        with (
            patch("loom.main.get_settings", return_value=bad),
            patch("loom.config.get_settings", return_value=bad),
        ):
            from loom.main import _lifespan, create_app

            application = create_app()
            with pytest.raises(ValueError, match="minio"):
                async with _lifespan(application):
                    pass
