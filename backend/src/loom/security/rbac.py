from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from loom.security.auth import decode_token


def _extract_token(request: Request) -> dict:
    """extract and decode jwt from authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid authorization header",
        )
    token = auth_header.removeprefix("Bearer ")
    try:
        return decode_token(token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from err


_token_dep = Depends(_extract_token)


def require_role(
    *roles: str,
) -> Callable[..., dict]:
    """dependency factory that checks user role."""

    def dependency(
        payload: dict = _token_dep,
    ) -> dict:
        if payload.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permissions",
            )
        return payload

    return dependency


def require_authenticated(
    payload: dict = _token_dep,
) -> dict:
    """dependency that verifies a valid token (any role)."""
    return payload


def get_current_user_id(token_payload: dict) -> str:
    """extract user_id from token payload."""
    return token_payload["sub"]
