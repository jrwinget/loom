import hmac

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

log = structlog.get_logger()

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_EXEMPT_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/register-user",
    "/api/v1/auth/mfa/challenge",
    "/api/v1/health",
    "/metrics",
}


class CSRFMiddleware:
    """double-submit cookie validation for mutating requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)

        if request.method not in _MUTATING_METHODS:
            await self.app(scope, receive, send)
            return

        if request.url.path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # skip csrf check for requests without a session
        # cookie (pure jwt/api-key auth)
        csrf_cookie = request.cookies.get("csrf_token")
        if csrf_cookie is None:
            await self.app(scope, receive, send)
            return

        csrf_header = request.headers.get("x-csrf-token", "")

        if not csrf_header or not hmac.compare_digest(
            csrf_cookie, csrf_header
        ):
            await log.awarning(
                "csrf validation failed",
                path=request.url.path,
                method=request.method,
            )
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF token mismatch"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
