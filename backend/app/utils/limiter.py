"""Rate limiting configuration for EventPilot AI using Flask-Limiter.

Provides application-level rate limiting for expensive operations (such as AI planning).
Enforces limits per authenticated user ID (g.user_id), with fallback to Bearer token or client IP.
"""

from typing import Optional
from flask import g, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def get_rate_limit_key() -> str:
    """Returns the unique rate-limiting key for the current request.

    Prefers the authenticated user ID (g.user_id) set by @require_auth.
    Falls back to Bearer token prefix or client IP address.
    """
    user_id = getattr(g, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return f"token:{token[:32]}"

    return get_remote_address()


limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri="memory://",
    strategy="fixed-window",
    headers_enabled=True,
)
