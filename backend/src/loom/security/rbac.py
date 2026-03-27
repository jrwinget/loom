from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select

from loom.security.auth import decode_token


async def _extract_token(request: Request) -> dict[str, Any]:
    """extract, decode, and verify jwt is not revoked."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid authorization header",
        )
    token = auth_header.removeprefix("Bearer ")
    try:
        payload = decode_token(token)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from err

    # check jti against revoked_tokens table
    jti = payload.get("jti")
    if jti:
        try:
            session_factory = request.app.state.db_session_factory
            if session_factory is not None:
                from loom.models.revoked_token import RevokedToken

                async with session_factory() as session:
                    result = await session.execute(
                        select(RevokedToken.id).where(
                            RevokedToken.jti == jti
                        )
                    )
                    if result.scalar_one_or_none() is not None:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="token has been revoked",
                        )
        except HTTPException:
            raise
        except Exception:
            # if db is unavailable, allow the request through
            # rather than blocking all authenticated requests
            pass

    return payload


_token_dep = Depends(_extract_token)


def require_role(
    *roles: str,
) -> Callable[..., Any]:
    """dependency factory that checks user role."""

    async def dependency(
        payload: dict[str, Any] = _token_dep,
    ) -> dict[str, Any]:
        if payload.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient permissions",
            )
        return payload

    return dependency


async def require_authenticated(
    payload: dict[str, Any] = _token_dep,
) -> dict[str, Any]:
    """dependency that verifies a valid token (any role)."""
    return payload


def get_current_user_id(token_payload: dict[str, Any]) -> str:
    """extract user_id from token payload."""
    return str(token_payload["sub"])
