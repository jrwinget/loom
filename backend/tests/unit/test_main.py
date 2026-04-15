"""tests for main app factory."""

from unittest.mock import patch

from fastapi import FastAPI

from loom.config import Settings, get_settings
from loom.main import create_app


def _make_settings(**overrides: object) -> Settings:
    """create test settings."""
    defaults = {
        "secret_key": ("test-secret-key-that-is-long-enough-for-validation"),
        "debug": False,
        "log_level": "info",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestCreateApp:
    """create_app returns FastAPI instance."""

    def test_returns_fastapi_instance(self) -> None:
        """factory produces a FastAPI app."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_has_title(self) -> None:
        """app title is Loom."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert app.title == "Loom"

    def test_app_version(self) -> None:
        """app version is set."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()
        assert app.version == "0.1.0"


class TestCors:
    """CORS configuration based on settings."""

    def test_cors_uses_configured_origins(self) -> None:
        """CORS middleware uses settings.cors_origins."""
        origins = [
            "http://localhost:3000",
            "https://app.example.com",
        ]
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(
                cors_origins=origins,
            ),
        ):
            app = create_app()

        from starlette.middleware.cors import CORSMiddleware

        cors_entries = [
            m for m in app.user_middleware if m.cls is CORSMiddleware
        ]
        assert len(cors_entries) == 1
        assert cors_entries[0].kwargs["allow_origins"] == origins


class TestSecurityHeaders:
    """security headers on all responses."""

    async def test_security_headers_present(self) -> None:
        """all 5 security headers are in the response."""
        import httpx

        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=True),
        ):
            app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/api/v1/health")

        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-XSS-Protection"] == "0"
        assert resp.headers["Referrer-Policy"] == (
            "strict-origin-when-cross-origin"
        )
        assert resp.headers["Permissions-Policy"] == (
            "camera=(), microphone=(), geolocation=()"
        )

    async def test_request_id_header_still_present(
        self,
    ) -> None:
        """X-Request-Id is still returned."""
        import httpx

        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(debug=True),
        ):
            app = create_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/api/v1/health")

        assert "X-Request-Id" in resp.headers
        rid = resp.headers["X-Request-Id"]
        assert len(rid) == 36  # uuid format


class TestRouterIncluded:
    """api router is mounted at /api/v1."""

    def test_api_routes_exist(self) -> None:
        """app has routes under /api/v1/."""
        get_settings.cache_clear()
        with patch(
            "loom.main.get_settings",
            return_value=_make_settings(),
        ):
            app = create_app()

        paths = [r.path for r in app.routes]
        assert any(p.startswith("/api/v1") for p in paths)
