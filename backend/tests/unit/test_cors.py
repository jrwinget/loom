"""tests for cors middleware configuration."""

from unittest.mock import patch

from starlette.middleware.cors import CORSMiddleware

from loom.config import Settings, get_settings
from loom.main import create_app


def _make_settings(**overrides: object) -> Settings:
    defaults = {
        "secret_key": ("test-secret-key-that-is-long-enough-for-validation"),
        "debug": False,
        "log_level": "info",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _cors_middleware(app: object) -> object:
    entries = [
        m
        for m in app.user_middleware  # type: ignore[attr-defined]
        if m.cls is CORSMiddleware
    ]
    assert len(entries) == 1
    return entries[0]


class TestCorsProduction:
    """cors in non-debug mode uses configured origins."""

    def test_uses_settings_cors_origins(self) -> None:
        """production should use settings.cors_origins."""
        origins = ["https://app.example.com"]
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(
                cors_origins=origins,
            ),
        ):
            app = create_app()

        mw = _cors_middleware(app)
        assert mw.kwargs["allow_origins"] == origins

    def test_not_empty_list(self) -> None:
        """regression: production must not fall back to []."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()

        mw = _cors_middleware(app)
        assert mw.kwargs["allow_origins"] != []

    def test_multiple_origins(self) -> None:
        """multiple configured origins are all passed."""
        origins = [
            "https://app.example.com",
            "https://admin.example.com",
        ]
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(
                cors_origins=origins,
            ),
        ):
            app = create_app()

        mw = _cors_middleware(app)
        assert mw.kwargs["allow_origins"] == origins


class TestCorsDebug:
    """cors in debug mode uses wildcard."""

    def test_debug_uses_wildcard(self) -> None:
        """debug=True should allow all origins."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=True),
        ):
            app = create_app()

        mw = _cors_middleware(app)
        assert mw.kwargs["allow_origins"] == ["*"]

    def test_debug_ignores_cors_origins_setting(self) -> None:
        """debug=True always uses wildcard, even with
        cors_origins configured."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(
                debug=True,
                cors_origins=["https://app.example.com"],
            ),
        ):
            app = create_app()

        mw = _cors_middleware(app)
        assert mw.kwargs["allow_origins"] == ["*"]
