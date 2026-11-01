"""Utilities and helper modules for EventPilot AI."""

from .errors import APIError, handle_api_error, register_error_handlers
from .auth import require_auth, require_event_owner, verify_supabase_token
from .limiter import limiter, get_rate_limit_key

__all__ = [
    "APIError",
    "handle_api_error",
    "register_error_handlers",
    "require_auth",
    "require_event_owner",
    "verify_supabase_token",
    "limiter",
    "get_rate_limit_key",
]
