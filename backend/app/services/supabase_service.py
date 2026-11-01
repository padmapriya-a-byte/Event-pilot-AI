"""Supabase Server-Side Admin & Request-Scoped User Service Clients.

Provides:
- SupabaseAdminService: Administrative Supabase client using Service Role Key.
  Used strictly on the Flask server for backend maintenance, webhooks, or elevated operations.
- create_user_client: Request-scoped Supabase client authenticated with a user's JWT
  and configured with the anon/publishable key.
"""

from typing import Optional, Any
from ..config import Config
from ..utils.errors import APIError

try:
    from supabase import create_client, Client, ClientOptions
except ImportError:
    create_client = None  # type: ignore
    Client = Any  # type: ignore
    ClientOptions = Any  # type: ignore


def create_user_client(
    user_token: str,
    url: Optional[str] = None,
    anon_key: Optional[str] = None,
) -> Client:
    """Creates a new, isolated request-scoped Supabase client authenticated with a user's JWT.

    Uses the configured Supabase URL and anon/publishable key.
    Ensures that per-user authentication headers never mutate or leak into the shared admin client.
    """
    clean_token = (user_token or "").replace("Bearer ", "").strip()
    if not clean_token:
        raise APIError(
            message="User authentication token is required for user-scoped Supabase client.",
            status_code=401,
            code="UNAUTHORIZED",
        )

    target_url = Config.SUPABASE_URL if url is None else url
    target_key = (Config.SUPABASE_ANON_KEY or Config.SUPABASE_SERVICE_ROLE_KEY) if anon_key is None else anon_key

    if not target_url or not target_key or target_key.startswith(("your_", "PASTE_")):
        raise APIError(
            message="Supabase service is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )

    if create_client is None:
        raise APIError(
            message="supabase package is not installed.",
            status_code=500,
            code="DEPENDENCY_MISSING",
        )

    auth_header = f"Bearer {clean_token}"
    options = None
    if ClientOptions is not Any:
        options = ClientOptions(
            headers={"Authorization": auth_header},
            auto_refresh_token=False,
            persist_session=False,
        )

    return create_client(target_url, target_key, options=options)


class SupabaseAdminService:
    """Wrapper around Supabase Admin Client."""

    def __init__(
        self,
        url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        anon_key: Optional[str] = None,
    ):
        self.url = url or Config.SUPABASE_URL
        self.service_role_key = service_role_key or Config.SUPABASE_SERVICE_ROLE_KEY
        self.anon_key = anon_key or Config.SUPABASE_ANON_KEY
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        """Lazy-initialize administrative Supabase client using Service Role Key."""
        if not self.is_configured:
            raise APIError(
                message="Supabase admin service is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
                status_code=503,
                code="SERVICE_UNAVAILABLE",
            )
        if self._client is None:
            if create_client is None:
                raise APIError(
                    message="supabase package is not installed.",
                    status_code=500,
                    code="DEPENDENCY_MISSING",
                )
            self._client = create_client(self.url, self.service_role_key)
        return self._client

    def get_user_client(
        self,
        user_token: str,
        anon_key: Optional[str] = None,
    ) -> Client:
        """Returns a new, request-scoped client authenticated with the user's JWT.

        Never mutates the shared admin client.
        """
        return create_user_client(
            user_token=user_token,
            url=self.url,
            anon_key=anon_key or self.anon_key,
        )

    @property
    def is_configured(self) -> bool:
        """Check whether Supabase service role credentials are provided."""
        return bool(
            self.url
            and self.service_role_key
            and not self.service_role_key.startswith("your_")
        )
