"""Authentication and Authorization Middleware for Supabase JWT verification.

Provides cryptographic JWT verification, user identity extraction (including
guest/anonymous status), and event-ownership authorization guards.
"""

from functools import wraps
import threading
from typing import Callable, Any, Dict, Optional
import uuid
import jwt
from jwt import PyJWKClient, PyJWKSet
from jwt.exceptions import (
    PyJWKClientError,
    PyJWKClientConnectionError,
    PyJWKSetError,
)
from flask import request, g, current_app
from .errors import APIError
from ..config import Config

ALLOWED_JWT_ALGORITHMS = {"HS256", "ES256", "RS256"}

_jwks_clients: Dict[str, PyJWKClient] = {}
_jwks_lock = threading.Lock()


def get_jwks_client(uri: str) -> PyJWKClient:
    """Returns or creates a cached PyJWKClient instance for the given JWKS URI."""
    with _jwks_lock:
        if uri not in _jwks_clients:
            _jwks_clients[uri] = PyJWKClient(
                uri=uri,
                cache_keys=True,
                max_cached_keys=32,
                cache_jwk_set=True,
                lifespan=300,
                timeout=10,
            )
        return _jwks_clients[uri]


def resolve_jwks_signing_key(kid: str, algorithm: Optional[str] = None) -> Any:
    """Resolves a public signing key from Supabase JWKS using the token's kid header.

    Supports:
    1. Direct injection of JWKS_DATA (dict of keys) in app config (for unit tests / mock).
    2. Direct injection of JWKS_CLIENT in app config (for unit tests / mock).
    3. Live/cached retrieval from SUPABASE_JWKS_URL or derived from SUPABASE_URL.
    """
    # 1. Configured/mock JWKS data (dict with "keys")
    jwks_data = current_app.config.get("JWKS_DATA")
    if jwks_data:
        try:
            jwk_set = PyJWKSet.from_dict(jwks_data)
            matching = PyJWKClient.match_kid(jwk_set.keys, kid)
            if not matching:
                raise APIError(
                    message=f"Signing key with kid '{kid}' not found in JWKS.",
                    status_code=401,
                    code="UNKNOWN_KID",
                )
            return matching.key
        except APIError:
            raise
        except Exception:
            raise APIError(
                message="Error parsing configured JWKS key set.",
                status_code=500,
                code="CONFIGURATION_ERROR",
            )

    # 2. Configured custom PyJWKClient
    custom_client = current_app.config.get("JWKS_CLIENT")
    if custom_client is not None:
        try:
            signing_key = custom_client.get_signing_key(kid)
            return signing_key.key
        except PyJWKClientConnectionError:
            raise APIError(
                message="Failed to connect to Supabase JWKS endpoint.",
                status_code=503,
                code="SERVICE_UNAVAILABLE",
            )
        except PyJWKClientError:
            raise APIError(
                message=f"Signing key with kid '{kid}' not found in JWKS.",
                status_code=401,
                code="UNKNOWN_KID",
            )
        except Exception:
            raise APIError(
                message="Failed to retrieve signing key from JWKS client.",
                status_code=500,
                code="CONFIGURATION_ERROR",
            )

    # 3. Determine JWKS URL
    jwks_url = current_app.config.get("SUPABASE_JWKS_URL", Config.SUPABASE_JWKS_URL)
    if not jwks_url:
        supabase_url = current_app.config.get("SUPABASE_URL", Config.SUPABASE_URL)
        jwks_url = Config.get_jwks_url(supabase_url)

    if not jwks_url:
        raise APIError(
            message="Supabase JWKS URL is not configured. Set SUPABASE_JWKS_URL or SUPABASE_URL.",
            status_code=500,
            code="CONFIGURATION_ERROR",
        )

    # 4. Fetch via PyJWKClient
    try:
        client = get_jwks_client(jwks_url)
        signing_key = client.get_signing_key(kid)
        return signing_key.key
    except PyJWKClientConnectionError:
        raise APIError(
            message="Failed to connect to Supabase JWKS endpoint.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )
    except PyJWKClientError:
        raise APIError(
            message=f"Signing key with kid '{kid}' not found in JWKS.",
            status_code=401,
            code="UNKNOWN_KID",
        )
    except Exception:
        raise APIError(
            message="Error communicating with Supabase JWKS service.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )


def get_jwt_verification_key(
    algorithm: Optional[str] = None,
    kid: Optional[str] = None,
) -> Any:
    """Returns the configured cryptographic key or secret for verifying Supabase JWTs.

    Security Rule:
      NEVER uses SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY for JWT signature verification.
    """
    algo = algorithm or current_app.config.get("SUPABASE_JWT_ALGORITHM", Config.SUPABASE_JWT_ALGORITHM)

    if algo.startswith("HS"):
        # Legacy symmetric token: strictly uses SUPABASE_JWT_SECRET.
        # NEVER falls back to SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY.
        secret = current_app.config.get("SUPABASE_JWT_SECRET", Config.SUPABASE_JWT_SECRET)
        if not secret:
            raise APIError(
                message="JWT verification secret is not configured on the server.",
                status_code=500,
                code="CONFIGURATION_ERROR",
            )
        return secret

    if kid:
        return resolve_jwks_signing_key(kid, algorithm=algo)

    # Fallback to configured static public key for RS256 / ES256 if kid is not in header
    public_key = current_app.config.get("SUPABASE_JWT_PUBLIC_KEY", Config.SUPABASE_JWT_PUBLIC_KEY)
    if not public_key:
        raise APIError(
            message=f"Public key for algorithm '{algo}' is not configured on the server.",
            status_code=500,
            code="CONFIGURATION_ERROR",
        )
    return public_key


def verify_supabase_token(raw_token: Optional[str] = None) -> Dict[str, Any]:
    """Cryptographically decodes and verifies a Supabase JWT.

    Supports:
      - Legacy HS256 tokens using SUPABASE_JWT_SECRET
      - Current ECC P-256 / ES256 tokens using Supabase JWKS (matching kid header)
      - Configured RS256 asymmetric public keys

    Validates:
      - Supported algorithm (HS256, ES256, RS256 only)
      - Key selection via JWT kid header for asymmetric tokens
      - Cryptographic signature
      - Expiration (exp)
      - Audience (aud)
      - Issuer (iss)
      - Subject (sub) user UUID presence
    """
    token = raw_token
    if not token:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise APIError(
                message="Missing or malformed Authorization header. Bearer token required.",
                status_code=401,
                code="UNAUTHORIZED",
            )
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or not parts[1].strip():
            raise APIError(
                message="Bearer token is empty or malformed.",
                status_code=401,
                code="UNAUTHORIZED",
            )
        token = parts[1].strip()

    # 1. Inspect unverified JWT header to determine algorithm and key ID (kid)
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise APIError(
            message="Token is malformed or could not be decoded.",
            status_code=401,
            code="MALFORMED_TOKEN",
        )

    if not isinstance(header, dict):
        raise APIError(
            message="Token is malformed or could not be decoded.",
            status_code=401,
            code="MALFORMED_TOKEN",
        )

    token_alg = header.get("alg")
    if not token_alg or str(token_alg).lower() == "none":
        raise APIError(
            message="Token algorithm is missing or invalid.",
            status_code=401,
            code="INVALID_ALGORITHM",
        )

    if token_alg not in ALLOWED_JWT_ALGORITHMS:
        raise APIError(
            message=f"Unsupported token algorithm: '{token_alg}'.",
            status_code=401,
            code="INVALID_ALGORITHM",
        )

    kid = header.get("kid")

    # 2. Select appropriate verification key
    if token_alg == "HS256":
        # Legacy symmetric token: strictly uses SUPABASE_JWT_SECRET.
        # NEVER falls back to SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY.
        verification_key = get_jwt_verification_key(algorithm="HS256")
    elif token_alg in ("ES256", "RS256"):
        # Asymmetric token: select key using the JWT kid header
        if not kid:
            # Check if static public key is explicitly configured for backward compatibility
            static_pub_key = current_app.config.get("SUPABASE_JWT_PUBLIC_KEY", Config.SUPABASE_JWT_PUBLIC_KEY)
            if static_pub_key:
                verification_key = static_pub_key
            else:
                raise APIError(
                    message="Token is missing required key ID ('kid') header for asymmetric verification.",
                    status_code=401,
                    code="INVALID_TOKEN",
                )
        else:
            verification_key = resolve_jwks_signing_key(kid, algorithm=token_alg)
    else:
        raise APIError(
            message=f"Unsupported token algorithm: '{token_alg}'.",
            status_code=401,
            code="INVALID_ALGORITHM",
        )

    # 3. Cryptographically decode and validate claims
    audience = current_app.config.get("SUPABASE_JWT_AUDIENCE", Config.SUPABASE_JWT_AUDIENCE)
    issuer = current_app.config.get("SUPABASE_JWT_ISSUER", Config.SUPABASE_JWT_ISSUER)

    decode_options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": bool(audience),
        "verify_iss": bool(issuer),
    }

    try:
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[token_alg],
            audience=audience if audience else None,
            issuer=issuer if issuer else None,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError:
        raise APIError(
            message="Token has expired. Please refresh your session.",
            status_code=401,
            code="TOKEN_EXPIRED",
        )
    except jwt.InvalidSignatureError:
        raise APIError(
            message="Token signature verification failed.",
            status_code=401,
            code="INVALID_SIGNATURE",
        )
    except jwt.InvalidAudienceError:
        raise APIError(
            message="Token audience does not match configured audience.",
            status_code=401,
            code="INVALID_AUDIENCE",
        )
    except jwt.InvalidIssuerError:
        raise APIError(
            message="Token issuer does not match configured issuer.",
            status_code=401,
            code="INVALID_ISSUER",
        )
    except jwt.DecodeError:
        raise APIError(
            message="Token is malformed or could not be decoded.",
            status_code=401,
            code="MALFORMED_TOKEN",
        )
    except jwt.InvalidTokenError as e:
        raise APIError(
            message=f"Invalid token: {str(e)}",
            status_code=401,
            code="INVALID_TOKEN",
        )

    # 4. Validate subject (user UUID) claim
    user_id = payload.get("sub")
    if not user_id:
        raise APIError(
            message="Token is missing required subject ('sub') claim.",
            status_code=401,
            code="INVALID_TOKEN",
        )

    return payload


def require_auth(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require a cryptographically valid Supabase Bearer token.

    Attaches verified identity to flask.g:
      - g.user_id: User UUID
      - g.user_email: User email (if present)
      - g.user_role: Supabase role
      - g.is_guest: Boolean indicating anonymous/guest session
      - g.jwt_claims: Complete decoded JWT payload
      - g.token: Raw bearer token string
    """

    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        payload = verify_supabase_token()

        g.user_id = str(payload["sub"])
        g.user_email = payload.get("email")
        g.user_role = payload.get("role")
        # In Supabase GoTrue, anonymous sessions carry is_anonymous: true in claims
        g.is_guest = bool(payload.get("is_anonymous", False))
        g.jwt_claims = payload
        g.token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

        return f(*args, **kwargs)

    return decorated_function


def default_event_resolver(event_id: str) -> Optional[Dict[str, Any]]:
    """Default database resolver that queries Supabase for event ownership.

    Fails closed on database or configuration errors by raising an APIError with 503
    instead of returning None, ensuring database downtime or network failure is not
    falsely treated as 404 Not Found.
    """
    from ..services.supabase_service import SupabaseAdminService

    admin_service = SupabaseAdminService()
    if not admin_service.is_configured:
        raise APIError(
            message="Database service is not configured.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )
    try:
        res = (
            admin_service.client.table("events")
            .select("id, owner_id, status, title, start_date, end_date")
            .eq("id", event_id)
            .execute()
        )
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except APIError:
        raise
    except Exception:
        raise APIError(
            message="Database query failed while verifying event ownership.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )


def require_event_owner(event_id_param: str = "event_id") -> Callable[..., Any]:
    """Decorator to authorize that the authenticated user owns the targeted event.

    Safety Rules:
      1. Rejects unauthenticated callers immediately (requires verified g.user_id).
      2. Does NOT trust client-supplied owner IDs in the request body.
      3. Validates UUID format of the event_id parameter.
      4. Queries the event record and verifies owner_id == g.user_id.
      5. Fails closed on resolver or infrastructure errors (no silent bypass or 404 mask).
      6. Attaches verified event to flask.g.current_event.
    """

    def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def decorated_function(*args: Any, **kwargs: Any) -> Any:
            # 1. Ensure user is authenticated
            if not getattr(g, "user_id", None):
                # If require_auth was not stacked prior to this decorator, verify token now
                payload = verify_supabase_token()
                g.user_id = str(payload["sub"])
                g.user_email = payload.get("email")
                g.user_role = payload.get("role")
                g.is_guest = bool(payload.get("is_anonymous", False))
                g.jwt_claims = payload

            # 2. Extract event_id parameter
            target_event_id = kwargs.get(event_id_param)
            if not target_event_id and request.view_args:
                target_event_id = request.view_args.get(event_id_param)
            if not target_event_id:
                target_event_id = request.args.get(event_id_param)
            if not target_event_id and request.is_json:
                json_body = request.get_json(silent=True) or {}
                target_event_id = json_body.get(event_id_param)

            if not target_event_id:
                raise APIError(
                    message=f"Missing required '{event_id_param}' parameter.",
                    status_code=400,
                    code="BAD_REQUEST",
                )

            # 3. Validate UUID format
            try:
                uuid_obj = uuid.UUID(str(target_event_id))
                normalized_event_id = str(uuid_obj)
            except ValueError:
                raise APIError(
                    message=f"Invalid '{event_id_param}' format. Must be a valid UUID.",
                    status_code=400,
                    code="BAD_REQUEST",
                )

            # 4. Resolve event and verify ownership (fail closed on error)
            resolver = current_app.config.get("EVENT_RESOLVER", default_event_resolver)
            try:
                event = resolver(normalized_event_id)
            except APIError:
                raise
            except Exception:
                raise APIError(
                    message="Failed to resolve event ownership due to an unexpected service error.",
                    status_code=503,
                    code="SERVICE_UNAVAILABLE",
                )

            if not event:
                raise APIError(
                    message=f"Event with id '{normalized_event_id}' not found.",
                    status_code=404,
                    code="NOT_FOUND",
                )

            event_owner_id = str(event.get("owner_id", ""))
            if event_owner_id != g.user_id:
                raise APIError(
                    message="Forbidden: You do not have permission to access this event.",
                    status_code=403,
                    code="FORBIDDEN",
                )

            # 5. Attach event to request context
            g.current_event = event

            return f(*args, **kwargs)

        return decorated_function

    return decorator
