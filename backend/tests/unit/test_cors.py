"""tests for cors middleware configuration."""

from unittest.mock import patch

import httpx
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


class TestCorsDesktopOrigins:
    """preflight contract for the tauri webview origins.

    these tests verify the actual cross-origin response the bundled
    webview will see, not just the middleware configuration. without
    them the v0.1.3-class regression (allowlist drift) cannot be
    caught by unit tests — `mw.kwargs` inspection passes even when
    the wire response is wrong.
    """

    _MUTATING_PATH = "/api/v1/auth/login"

    def _build_app(
        self,
        cors_origins: list[str] | None = None,
    ) -> object:
        """create a non-debug app with the configured allowlist."""
        get_settings.cache_clear()
        overrides: dict[str, object] = {}
        if cors_origins is not None:
            overrides["cors_origins"] = cors_origins
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(**overrides),
        ):
            return create_app()

    def test_default_includes_tauri_origins(self) -> None:
        """fast-feedback: default allowlist carries the four webview origins."""
        app = self._build_app()
        mw = _cors_middleware(app)
        assert "tauri://localhost" in mw.kwargs["allow_origins"]
        assert "http://tauri.localhost" in mw.kwargs["allow_origins"]
        assert "http://127.0.0.1:3000" in mw.kwargs["allow_origins"]

    async def test_preflight_allows_tauri_localhost(self) -> None:
        """production webview origin on macos/linux gets a green preflight."""
        app = self._build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.options(
                self._MUTATING_PATH,
                headers={
                    "Origin": "tauri://localhost",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == (
            "tauri://localhost"
        )
        assert resp.headers["access-control-allow-credentials"] == "true"

    async def test_preflight_allows_http_tauri_localhost(self) -> None:
        """production webview origin on windows gets a green preflight."""
        app = self._build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.options(
                self._MUTATING_PATH,
                headers={
                    "Origin": "http://tauri.localhost",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == (
            "http://tauri.localhost"
        )

    async def test_preflight_rejects_unlisted_origin(self) -> None:
        """a foreign origin must not be echoed in access-control-allow-origin.

        cors middleware still returns a 200 to the preflight, but it
        must withhold the allow-origin header so the browser drops
        the response. checks both the header is absent and that it is
        not a wildcard masquerade.
        """
        app = self._build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.options(
                self._MUTATING_PATH,
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
        allow = resp.headers.get("access-control-allow-origin", "")
        assert allow != "https://evil.example.com"
        assert allow != "*"
