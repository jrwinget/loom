from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from loom.security.auth import decode_token


def _get_user_key(request: Request) -> str:
    """extract user id from jwt for per-user rate limiting.

    falls back to ip address if no valid token is present.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header.removeprefix("Bearer ")
            payload = decode_token(token)
            return f"user:{payload['sub']}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
)

# per-user limiter for authenticated endpoints
user_limiter = Limiter(
    key_func=_get_user_key,
    default_limits=[],
)
