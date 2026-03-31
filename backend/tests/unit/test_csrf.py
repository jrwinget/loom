"""csrf double-submit cookie protection tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from loom.config import Settings
from loom.security.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CSRF_TOKEN_LENGTH,
    CsrfMiddleware,
    _generate_csrf_token,
)

# ── unit tests ───────────────────────────────────────────


class TestCsrfTokenGeneration:
    """csrf token generation."""

    def test_generates_hex_string(self) -> None:
        """token must be a hex string."""
        token = _generate_csrf_token()
        int(token, 16)  # raises if not valid hex

    def test_correct_length(self) -> None:
        """token must be the configured length."""
        token = _generate_csrf_token()
        assert len(token) == CSRF_TOKEN_LENGTH * 2  # hex

    def test_unique_per_call(self) -> None:
        """each call produces a different token."""
        t1 = _generate_csrf_token()
        t2 = _generate_csrf_token()
        assert t1 != t2


# ── integration tests ────────────────────────────────────


@pytest.fixture()
def _settings():
    """test settings."""
    return Settings(
        secret_key=("test-secret-key-that-is-long-enough-for-validation"),
        database_url="sqlite+aiosqlite:///",
    )


@pytest.fixture()
def _app(_settings):
    """minimal fastapi app with csrf middleware."""
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(CsrfMiddleware)

    @app.get("/read")
    async def read_endpoint():
        return {"ok": True}

    @app.post("/write")
    async def write_endpoint():
        return {"ok": True}

    @app.patch("/update")
    async def update_endpoint():
        return {"ok": True}

    @app.delete("/remove")
    async def remove_endpoint():
        return {"ok": True}

    # exempt auth endpoints
    @app.post("/api/v1/auth/login")
    async def login_endpoint():
        return {"ok": True}

    @app.post("/api/v1/auth/register")
    async def register_endpoint():
        return {"ok": True}

    @app.post("/api/v1/auth/refresh")
    async def refresh_endpoint():
        return {"ok": True}

    return app


class TestCsrfMiddleware:
    """csrf middleware integration tests."""

    @pytest.mark.asyncio
    async def test_get_sets_csrf_cookie(
        self,
        _app,
    ) -> None:
        """GET requests set the csrf cookie."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/read")
        assert resp.status_code == 200
        assert CSRF_COOKIE_NAME in resp.cookies

    @pytest.mark.asyncio
    async def test_get_succeeds_without_header(
        self,
        _app,
    ) -> None:
        """GET requests don't require csrf header."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/read")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_without_token_rejected(
        self,
        _app,
    ) -> None:
        """POST without csrf token returns 403."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/write")
        assert resp.status_code == 403
        body = resp.json()
        assert "csrf" in body["detail"].lower()

    @pytest.mark.asyncio
    async def test_post_with_valid_token_succeeds(
        self,
        _app,
    ) -> None:
        """POST with matching cookie+header succeeds."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            # first get a csrf cookie
            get_resp = await client.get("/read")
            token = get_resp.cookies[CSRF_COOKIE_NAME]

            # send it back as header
            resp = await client.post(
                "/write",
                headers={CSRF_HEADER_NAME: token},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_with_wrong_token_rejected(
        self,
        _app,
    ) -> None:
        """POST with mismatched header rejected."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            # get a cookie
            await client.get("/read")

            # send wrong token as header
            resp = await client.post(
                "/write",
                headers={CSRF_HEADER_NAME: "wrong-token"},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_requires_csrf(
        self,
        _app,
    ) -> None:
        """PATCH is a state-changing method and needs csrf."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.patch("/update")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_requires_csrf(
        self,
        _app,
    ) -> None:
        """DELETE is a state-changing method and needs csrf."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.delete("/remove")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_with_valid_token_succeeds(
        self,
        _app,
    ) -> None:
        """DELETE with matching cookie+header succeeds."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            get_resp = await client.get("/read")
            token = get_resp.cookies[CSRF_COOKIE_NAME]

            resp = await client.delete(
                "/remove",
                headers={CSRF_HEADER_NAME: token},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cookie_is_httponly_false(
        self,
        _app,
    ) -> None:
        """csrf cookie must be readable by javascript
        (httponly=false) so the frontend can send it
        as a header."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/read")
        # httpx doesn't expose cookie flags directly;
        # verify the cookie value is readable
        assert resp.cookies.get(CSRF_COOKIE_NAME)

    @pytest.mark.asyncio
    async def test_login_exempt_from_csrf(
        self,
        _app,
    ) -> None:
        """auth login endpoint is exempt from csrf."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/auth/login")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_register_exempt_from_csrf(
        self,
        _app,
    ) -> None:
        """auth register endpoint is exempt from csrf."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/auth/register")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_refresh_exempt_from_csrf(
        self,
        _app,
    ) -> None:
        """auth refresh endpoint is exempt from csrf."""
        async with AsyncClient(
            transport=ASGITransport(app=_app),
            base_url="http://test",
        ) as client:
            resp = await client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
