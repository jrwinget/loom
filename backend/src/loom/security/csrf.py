"""csrf double-submit cookie middleware.

generates a random token, sets it as a non-httponly cookie,
and validates that state-changing requests (POST, PUT, PATCH,
DELETE) include the same token in the X-CSRF-Token header.

safe methods (GET, HEAD, OPTIONS) are exempt and receive
a fresh cookie on each response.  auth endpoints (login,
register, refresh) are also exempt since they establish
the session rather than act within one.
"""

import secrets

from fastapi import Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.responses import JSONResponse

CSRF_COOKIE_NAME = "loom_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_TOKEN_LENGTH = 32  # bytes; hex-encoded = 64 chars

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# paths exempt from csrf validation — these establish
# sessions rather than acting within one
_EXEMPT_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/health",
    }
)


def _generate_csrf_token() -> str:
    """generate a cryptographically random csrf token."""
    return secrets.token_hex(CSRF_TOKEN_LENGTH)


class CsrfMiddleware(BaseHTTPMiddleware):
    """double-submit cookie csrf protection."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method in _SAFE_METHODS:
            response = await call_next(request)
            # set a fresh csrf cookie for the client to read
            if CSRF_COOKIE_NAME not in request.cookies:
                token = _generate_csrf_token()
                response.set_cookie(
                    CSRF_COOKIE_NAME,
                    token,
                    httponly=False,  # js must read it
                    samesite="strict",
                    secure=False,  # allow http in dev
                    path="/",
                )
            return response

        # exempt auth endpoints that establish sessions
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        # state-changing method: validate csrf token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)

        if (
            not cookie_token
            or not header_token
            or not secrets.compare_digest(cookie_token, header_token)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )

        response = await call_next(request)
        return response
