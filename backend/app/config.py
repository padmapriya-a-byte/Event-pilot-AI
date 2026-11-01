"""EventPilot AI - Backend Configuration Loader.

Loads application settings and credentials from environment variables.
Sensitive credentials (Gemini API Key, Supabase Service Role Key, JWT Secret) are restricted to the server.
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load .env file explicitly from the backend directory
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=env_path)


class Config:
    """Base application configuration."""

    ENV: str = os.getenv("FLASK_ENV", "development")
    DEBUG: bool = ENV == "development"
    TESTING: bool = False
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-secret-key-change-me")
    PORT: int = int(os.getenv("PORT", "5000"))

    # CORS settings - allowed frontend origins
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]

    # Google Gemini AI settings (Server-Side Only)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    # Supabase Server-Side Admin settings (Server-Side Only)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_ANON_KEY: str = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )

    # Supabase JWT Verification Configuration (Server-Side Only)
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    SUPABASE_JWT_ALGORITHM: str = os.getenv("SUPABASE_JWT_ALGORITHM", "HS256")
    SUPABASE_JWT_AUDIENCE: Optional[str] = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    SUPABASE_JWT_ISSUER: Optional[str] = os.getenv("SUPABASE_JWT_ISSUER", None)
    SUPABASE_JWT_PUBLIC_KEY: Optional[str] = os.getenv("SUPABASE_JWT_PUBLIC_KEY", None)
    SUPABASE_JWKS_URL: Optional[str] = os.getenv("SUPABASE_JWKS_URL", None)

    # Supabase Storage settings
    STORAGE_EXPORTS_BUCKET: str = os.getenv("STORAGE_EXPORTS_BUCKET", "plan-exports")

    # Guest Session Policy
    GUEST_INACTIVITY_RETENTION_DAYS: int = int(
        os.getenv("GUEST_INACTIVITY_RETENTION_DAYS", "30")
    )

    # Application-level Rate Limiting (Flask-Limiter)
    RATELIMIT_STORAGE_URI: str = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_AI_LIMIT: str = os.getenv("RATELIMIT_AI_LIMIT", "5 per minute")
    RATELIMIT_STRATEGY: str = os.getenv("RATELIMIT_STRATEGY", "fixed-window")
    RATELIMIT_HEADERS_ENABLED: bool = True

    @classmethod
    def get_jwks_url(cls, base_url: Optional[str] = None) -> Optional[str]:
        """Returns the configured or derived Supabase JWKS endpoint URL."""
        if cls.SUPABASE_JWKS_URL:
            return cls.SUPABASE_JWKS_URL
        target_url = base_url or cls.SUPABASE_URL
        if target_url and not target_url.startswith("https://your-"):
            return f"{target_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    @classmethod
    def is_gemini_configured(cls) -> bool:
        """Check if Gemini AI credentials are configured."""
        return bool(cls.GEMINI_API_KEY and not cls.GEMINI_API_KEY.startswith("your_"))

    @classmethod
    def is_supabase_configured(cls) -> bool:
        """Check if Supabase server credentials are configured."""
        return bool(
            cls.SUPABASE_URL
            and cls.SUPABASE_SERVICE_ROLE_KEY
            and not cls.SUPABASE_SERVICE_ROLE_KEY.startswith(("your_", "PASTE_"))
        )

    @classmethod
    def is_supabase_anon_configured(cls) -> bool:
        """Check if Supabase anon / publishable credentials are configured."""
        return bool(
            cls.SUPABASE_URL
            and cls.SUPABASE_ANON_KEY
            and not cls.SUPABASE_ANON_KEY.startswith(("your_", "PASTE_"))
        )

    @classmethod
    def validate_production_invariants(cls) -> None:
        """Enforces security invariants in production environments.

        Prevents startup if default insecure secrets or unconfigured credentials
        are detected when running in production mode.
        """
        if cls.ENV == "production":
            insecure_key = "dev-insecure-secret-key-change-me"
            if not cls.SECRET_KEY or cls.SECRET_KEY == insecure_key:
                raise ValueError(
                    "Production configuration error: SECRET_KEY must be set to a secure unique random string."
                )

            if (
                not cls.SUPABASE_JWT_SECRET
                and not cls.SUPABASE_JWT_PUBLIC_KEY
                and not cls.SUPABASE_JWKS_URL
            ):
                raise ValueError(
                    "Production configuration error: SUPABASE_JWT_SECRET or SUPABASE_JWT_PUBLIC_KEY must be configured for JWT verification."
                )

            if not cls.SUPABASE_URL or cls.SUPABASE_URL.startswith("https://your-"):
                raise ValueError(
                    "Production configuration error: SUPABASE_URL must be configured."
                )

            if not cls.SUPABASE_SERVICE_ROLE_KEY or cls.SUPABASE_SERVICE_ROLE_KEY.startswith(("your_", "PASTE_")):
                raise ValueError(
                    "Production configuration error: SUPABASE_SERVICE_ROLE_KEY must be configured."
                )
