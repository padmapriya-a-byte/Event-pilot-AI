"""EventPilot AI - Automated Test Suite for Authentication & Authorization.

Tests cryptographic Supabase JWT verification, claim extraction, guest session
identification, event-ownership authorization guards, and production configuration invariants.
"""

import os
import sys
import time
import uuid
import base64
import unittest
from unittest.mock import patch, MagicMock

# Ensure backend directory is in sys.path when running tests from repo root
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import jwt
from jwt.exceptions import PyJWKClientConnectionError
from flask import Flask, jsonify, g, Blueprint
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives import serialization

from app import create_app
from app.config import Config
from app.utils.auth import (
    require_auth,
    require_event_owner,
    verify_supabase_token,
    get_jwt_verification_key,
)
from app.utils.errors import APIError, register_error_handlers


class TestConfig(Config):
    """Test configuration overriding base settings."""
    TESTING = True
    ENV = "testing"
    SECRET_KEY = "test-secret-key-for-unit-testing"
    SUPABASE_JWT_SECRET = "super-secret-jwt-signing-key-for-testing"
    SUPABASE_JWT_ALGORITHM = "HS256"
    SUPABASE_JWT_AUDIENCE = "authenticated"
    SUPABASE_JWT_ISSUER = None
    SUPABASE_JWT_PUBLIC_KEY = None


class AuthenticationTestCase(unittest.TestCase):
    """Test suite for Supabase JWT verification and @require_auth decorator."""

    @classmethod
    def setUpClass(cls):
        # Generate an RSA key pair for asymmetric JWT tests
        cls.rsa_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        cls.rsa_private_pem = cls.rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        cls.rsa_public_pem = (
            cls.rsa_private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )

        # Generate a second key pair to test invalid asymmetric signature
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.rsa_other_private_pem = other_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        # Generate EC P-256 key pairs for ES256 Supabase JWKS tests
        def b64url(b: bytes) -> str:
            return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

        # 1. Primary EC Key
        cls.ec_private_key = ec.generate_private_key(ec.SECP256R1())
        nums1 = cls.ec_private_key.public_key().public_numbers()
        cls.ec_kid = "supabase-ec-key-primary"
        cls.ec_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url(nums1.x.to_bytes(32, "big")),
            "y": b64url(nums1.y.to_bytes(32, "big")),
            "kid": cls.ec_kid,
            "use": "sig",
            "alg": "ES256",
        }

        # 2. Secondary EC Key (to test key selection by kid among multiple keys)
        cls.ec_second_private_key = ec.generate_private_key(ec.SECP256R1())
        nums2 = cls.ec_second_private_key.public_key().public_numbers()
        cls.ec_second_kid = "supabase-ec-key-secondary"
        cls.ec_second_jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url(nums2.x.to_bytes(32, "big")),
            "y": b64url(nums2.y.to_bytes(32, "big")),
            "kid": cls.ec_second_kid,
            "use": "sig",
            "alg": "ES256",
        }

        # 3. Unauthorized EC Key (not in JWKS, to test invalid signature)
        cls.ec_other_private_key = ec.generate_private_key(ec.SECP256R1())

        # Complete JWKS document matching Supabase format
        cls.jwks_data = {
            "keys": [cls.ec_jwk, cls.ec_second_jwk],
        }

    def setUp(self):
        """Create a fresh Flask application and test client for each test."""
        self.app = create_app(TestConfig)
        self.app.config["JWKS_DATA"] = self.jwks_data
        self.client = self.app.test_client()

        # In-memory mock database for event ownership tests
        self.events_db = {}

        def mock_event_resolver(event_id: str):
            return self.events_db.get(event_id)

        self.app.config["EVENT_RESOLVER"] = mock_event_resolver

        # Register test endpoints that use the auth decorators
        test_bp = Blueprint("test_auth_routes", __name__)

        @test_bp.route("/api/test/protected", methods=["GET"])
        @require_auth
        def protected_route():
            return jsonify({
                "status": "success",
                "user_id": g.user_id,
                "email": g.user_email,
                "role": g.user_role,
                "is_guest": g.is_guest,
            })

        @test_bp.route("/api/test/events/<event_id>/details", methods=["GET"])
        @require_auth
        @require_event_owner("event_id")
        def event_details_route(event_id):
            return jsonify({
                "status": "success",
                "event_id": event_id,
                "title": g.current_event.get("title"),
            })

        @test_bp.route("/api/test/events-direct/<event_id>", methods=["GET"])
        @require_event_owner("event_id")
        def direct_event_route(event_id):
            return jsonify({
                "status": "success",
                "event_id": event_id,
                "owner_id": g.current_event.get("owner_id"),
            })

        self.app.register_blueprint(test_bp)

    def _create_token(
        self,
        sub: str = "d3b07384-d113-4a00-9978-83149c9f2258",
        exp_offset: int = 3600,
        aud: str = "authenticated",
        iss: str = None,
        email: str = "user@example.com",
        role: str = "authenticated",
        is_anonymous: bool = False,
        secret: str = None,
        algorithm: str = "HS256",
        key=None,
    ) -> str:
        """Helper to create test JWT tokens."""
        payload = {
            "sub": sub,
            "exp": int(time.time()) + exp_offset,
            "iat": int(time.time()),
        }
        if aud is not None:
            payload["aud"] = aud
        if iss is not None:
            payload["iss"] = iss
        if email is not None:
            payload["email"] = email
        if role is not None:
            payload["role"] = role
        if is_anonymous:
            payload["is_anonymous"] = True

        signing_key = key if key is not None else (secret or self.app.config["SUPABASE_JWT_SECRET"])
        return jwt.encode(payload, signing_key, algorithm=algorithm)

    def _create_es256_token(
        self,
        sub: str = "d3b07384-d113-4a00-9978-83149c9f2258",
        exp_offset: int = 3600,
        aud: str = "authenticated",
        iss: str = None,
        email: str = "user@example.com",
        role: str = "authenticated",
        is_anonymous: bool = False,
        kid: Optional[str] = "supabase-ec-key-primary",
        key=None,
    ) -> str:
        """Helper to create test ES256 JWT tokens."""
        payload = {
            "sub": sub,
            "exp": int(time.time()) + exp_offset,
            "iat": int(time.time()),
        }
        if aud is not None:
            payload["aud"] = aud
        if iss is not None:
            payload["iss"] = iss
        if email is not None:
            payload["email"] = email
        if role is not None:
            payload["role"] = role
        if is_anonymous:
            payload["is_anonymous"] = True

        signing_key = key if key is not None else self.ec_private_key
        headers = {}
        if kid is not None:
            headers["kid"] = kid
        return jwt.encode(payload, signing_key, algorithm="ES256", headers=headers)

    # =========================================================================
    # 1. JWT Authentication Tests
    # =========================================================================

    def test_missing_authorization_header(self):
        """Request without Authorization header returns 401 UNAUTHORIZED."""
        response = self.client.get("/api/test/protected")
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")
        self.assertIn("Missing or malformed Authorization header", data["error"]["message"])

    def test_malformed_authorization_header_no_bearer(self):
        """Header without 'Bearer ' prefix returns 401 UNAUTHORIZED."""
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_empty_bearer_token(self):
        """Header with 'Bearer ' but no token returns 401 UNAUTHORIZED."""
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": "Bearer  "},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_malformed_token_string(self):
        """Invalid non-JWT string returns 401 MALFORMED_TOKEN."""
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "MALFORMED_TOKEN")

    def test_invalid_signature_rejected(self):
        """Token signed with wrong secret returns 401 INVALID_SIGNATURE."""
        bad_token = self._create_token(secret="completely-wrong-secret-with-at-least-32-bytes")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_SIGNATURE")

    def test_expired_token_rejected(self):
        """Token whose exp timestamp has passed returns 401 TOKEN_EXPIRED."""
        expired_token = self._create_token(exp_offset=-3600)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "TOKEN_EXPIRED")

    def test_invalid_audience_rejected(self):
        """Token with mismatched audience returns 401 INVALID_AUDIENCE."""
        bad_aud_token = self._create_token(aud="unrecognized_audience")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {bad_aud_token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_AUDIENCE")

    def test_invalid_issuer_rejected(self):
        """Token with mismatched issuer returns 401 INVALID_ISSUER when issuer enforcement is active."""
        self.app.config["SUPABASE_JWT_ISSUER"] = "https://myproject.supabase.co/auth/v1"
        bad_iss_token = self._create_token(iss="https://evil.supabase.co/auth/v1")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {bad_iss_token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_ISSUER")

    def test_valid_issuer_accepted(self):
        """Token with matching issuer succeeds when issuer enforcement is active."""
        expected_issuer = "https://myproject.supabase.co/auth/v1"
        self.app.config["SUPABASE_JWT_ISSUER"] = expected_issuer
        valid_iss_token = self._create_token(iss=expected_issuer)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {valid_iss_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")

    def test_missing_sub_claim_rejected(self):
        """Token missing 'sub' claim returns 401 INVALID_TOKEN."""
        payload = {
            "exp": int(time.time()) + 3600,
            "aud": "authenticated",
            "email": "user@example.com",
        }
        token_no_sub = jwt.encode(payload, self.app.config["SUPABASE_JWT_SECRET"], algorithm="HS256")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token_no_sub}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_TOKEN")
        self.assertIn("missing required subject", data["error"]["message"].lower())

    def test_valid_standard_user_token(self):
        """Valid standard token populates user_id, email, role, and is_guest=False."""
        user_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        token = self._create_token(
            sub=user_uuid,
            email="organizer@eventpilot.ai",
            role="authenticated",
            is_anonymous=False,
        )
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user_id"], user_uuid)
        self.assertEqual(data["email"], "organizer@eventpilot.ai")
        self.assertEqual(data["role"], "authenticated")
        self.assertFalse(data["is_guest"])

    def test_valid_anonymous_guest_token(self):
        """Valid anonymous session token sets is_guest=True."""
        guest_uuid = "e7b0c3d4-e5f6-7890-abcd-ef1234567891"
        token = self._create_token(
            sub=guest_uuid,
            email=None,
            role="authenticated",
            is_anonymous=True,
        )
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user_id"], guest_uuid)
        self.assertTrue(data["is_guest"])

    def test_asymmetric_rs256_verification(self):
        """Supports RS256 asymmetric public-key verification when configured."""
        self.app.config["SUPABASE_JWT_ALGORITHM"] = "RS256"
        self.app.config["SUPABASE_JWT_PUBLIC_KEY"] = self.rsa_public_pem

        user_uuid = "c3b07384-d113-4a00-9978-83149c9f2259"
        rs256_token = self._create_token(
            sub=user_uuid,
            algorithm="RS256",
            key=self.rsa_private_pem,
        )

        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {rs256_token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user_id"], user_uuid)

        # Token signed with another RSA private key must be rejected
        other_rs256_token = self._create_token(
            sub=user_uuid,
            algorithm="RS256",
            key=self.rsa_other_private_pem,
        )
        bad_response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {other_rs256_token}"},
        )
        self.assertEqual(bad_response.status_code, 401)
        bad_data = bad_response.get_json()
        self.assertEqual(bad_data["error"]["code"], "INVALID_SIGNATURE")

    # =========================================================================
    # 2. Event Ownership Authorization Tests
    # =========================================================================

    def test_event_owner_unauthenticated_rejected(self):
        """Unauthenticated caller to event-guarded route is rejected with 401."""
        event_id = str(uuid.uuid4())
        response = self.client.get(f"/api/test/events/{event_id}/details")
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_event_owner_missing_event_id(self):
        """Route missing event_id param fails with 400 BAD_REQUEST."""
        token = self._create_token()

        # Call endpoint without parameter via direct handler
        with self.app.test_request_context("/api/test/events", headers={"Authorization": f"Bearer {token}"}):
            @require_event_owner("non_existent_param")
            def dummy_handler():
                return "ok"

            with self.assertRaises(APIError) as cm:
                dummy_handler()
            self.assertEqual(cm.exception.status_code, 400)
            self.assertEqual(cm.exception.code, "BAD_REQUEST")

    def test_event_owner_invalid_uuid_rejected(self):
        """Event ID that is not a valid UUID is rejected with 400 BAD_REQUEST."""
        token = self._create_token()
        response = self.client.get(
            "/api/test/events/not-a-valid-uuid/details",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "BAD_REQUEST")
        self.assertIn("Must be a valid UUID", data["error"]["message"])

    def test_event_not_found_returns_404(self):
        """Non-existent event UUID returns 404 NOT_FOUND."""
        token = self._create_token()
        unknown_event_id = str(uuid.uuid4())
        response = self.client.get(
            f"/api/test/events/{unknown_event_id}/details",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "NOT_FOUND")

    def test_event_owned_by_another_user_forbidden(self):
        """Caller accessing an event owned by another user is rejected with 403 FORBIDDEN."""
        event_id = str(uuid.uuid4())
        actual_owner_id = str(uuid.uuid4())
        different_caller_id = str(uuid.uuid4())

        self.events_db[event_id] = {
            "id": event_id,
            "owner_id": actual_owner_id,
            "title": "Confidential Board Meeting",
            "status": "draft",
        }

        token = self._create_token(sub=different_caller_id)
        response = self.client.get(
            f"/api/test/events/{event_id}/details",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "FORBIDDEN")
        self.assertIn("do not have permission", data["error"]["message"])

    def test_event_owned_by_caller_allowed(self):
        """Legitimate event owner can access their event successfully."""
        event_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())

        self.events_db[event_id] = {
            "id": event_id,
            "owner_id": owner_id,
            "title": "Tech Conference 2026",
            "status": "published",
        }

        token = self._create_token(sub=owner_id)
        response = self.client.get(
            f"/api/test/events/{event_id}/details",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["title"], "Tech Conference 2026")

    def test_event_owner_decorator_standalone_authentication(self):
        """require_event_owner standalone initiates token verification if require_auth was not stacked."""
        event_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())

        self.events_db[event_id] = {
            "id": event_id,
            "owner_id": owner_id,
            "title": "Direct Event Access",
            "status": "draft",
        }

        token = self._create_token(sub=owner_id)
        response = self.client.get(
            f"/api/test/events-direct/{event_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["owner_id"], owner_id)

    def test_spoofed_owner_id_in_body_is_ignored(self):
        """Client-supplied owner_id in body/payload cannot override actual event owner."""
        event_id = str(uuid.uuid4())
        real_owner_id = str(uuid.uuid4())
        attacker_id = str(uuid.uuid4())

        self.events_db[event_id] = {
            "id": event_id,
            "owner_id": real_owner_id,
            "title": "Target Event",
        }

        # Attacker attempts to claim ownership by supplying owner_id in JSON payload
        token = self._create_token(sub=attacker_id)
        response = self.client.get(
            f"/api/test/events/{event_id}/details",
            headers={"Authorization": f"Bearer {token}"},
            json={"owner_id": attacker_id},
        )
        self.assertEqual(response.status_code, 403)

    # =========================================================================
    # 3. Production Configuration Security Invariant Tests
    # =========================================================================

    def test_production_fails_with_insecure_default_secret_key(self):
        """validate_production_invariants raises ValueError if SECRET_KEY is default in production."""
        class MockProdConfig(Config):
            ENV = "production"
            SECRET_KEY = "dev-insecure-secret-key-change-me"
            SUPABASE_JWT_SECRET = "some-jwt-secret"
            SUPABASE_URL = "https://my-real-project.supabase.co"
            SUPABASE_SERVICE_ROLE_KEY = "ey-valid-service-role-key"

        with self.assertRaises(ValueError) as cm:
            MockProdConfig.validate_production_invariants()
        self.assertIn("SECRET_KEY must be set", str(cm.exception))

    def test_production_fails_with_missing_jwt_secrets(self):
        """validate_production_invariants raises ValueError if JWT secret/key is missing in production."""
        class MockProdConfig(Config):
            ENV = "production"
            SECRET_KEY = "a-very-strong-production-secret-key"
            SUPABASE_JWT_SECRET = ""
            SUPABASE_JWT_PUBLIC_KEY = None
            SUPABASE_JWKS_URL = None
            SUPABASE_URL = "https://my-real-project.supabase.co"
            SUPABASE_SERVICE_ROLE_KEY = "ey-valid-service-role-key"

        with self.assertRaises(ValueError) as cm:
            MockProdConfig.validate_production_invariants()
        self.assertIn("SUPABASE_JWT_SECRET or SUPABASE_JWT_PUBLIC_KEY must be configured", str(cm.exception))

    def test_production_fails_with_unconfigured_supabase_url(self):
        """validate_production_invariants raises ValueError if SUPABASE_URL is empty or template."""
        class MockProdConfig(Config):
            ENV = "production"
            SECRET_KEY = "a-very-strong-production-secret-key"
            SUPABASE_JWT_SECRET = "valid-jwt-secret"
            SUPABASE_URL = "https://your-project-id.supabase.co"
            SUPABASE_SERVICE_ROLE_KEY = "ey-valid-service-role-key"

        with self.assertRaises(ValueError) as cm:
            MockProdConfig.validate_production_invariants()
        self.assertIn("SUPABASE_URL must be configured", str(cm.exception))

    def test_production_fails_with_unconfigured_service_role_key(self):
        """validate_production_invariants raises ValueError if SUPABASE_SERVICE_ROLE_KEY is template."""
        class MockProdConfig(Config):
            ENV = "production"
            SECRET_KEY = "a-very-strong-production-secret-key"
            SUPABASE_JWT_SECRET = "valid-jwt-secret"
            SUPABASE_URL = "https://real-project.supabase.co"
            SUPABASE_SERVICE_ROLE_KEY = "your_supabase_service_role_key_here"

        with self.assertRaises(ValueError) as cm:
            MockProdConfig.validate_production_invariants()
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY must be configured", str(cm.exception))

    def test_production_passes_with_valid_secure_configuration(self):
        """validate_production_invariants succeeds when all production invariants are satisfied."""
        class MockProdConfig(Config):
            ENV = "production"
            SECRET_KEY = "a-very-strong-unique-production-secret-key"
            SUPABASE_JWT_SECRET = "valid-secure-jwt-secret"
            SUPABASE_URL = "https://production-eventpilot.supabase.co"
            SUPABASE_SERVICE_ROLE_KEY = "ey-production-service-role-key-value"

        # Should not raise any exception
        MockProdConfig.validate_production_invariants()

    def test_development_mode_permits_dev_defaults(self):
        """validate_production_invariants does not fail in development mode with dev defaults."""
        class MockDevConfig(Config):
            ENV = "development"
            SECRET_KEY = "dev-insecure-secret-key-change-me"
            SUPABASE_JWT_SECRET = ""
            SUPABASE_URL = ""
            SUPABASE_SERVICE_ROLE_KEY = ""

        # Should not raise in development
        MockDevConfig.validate_production_invariants()

    # =========================================================================
    # 4. Supabase JWKS & ECC P-256 (ES256) JWT Verification Tests
    # =========================================================================

    def test_es256_valid_token_success(self):
        """Valid ES256 token verified via JWKS matching kid succeeds and populates identity."""
        user_uuid = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
        token = self._create_es256_token(
            sub=user_uuid,
            email="ec_user@eventpilot.ai",
            role="authenticated",
            kid=self.ec_kid,
        )
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user_id"], user_uuid)
        self.assertEqual(data["email"], "ec_user@eventpilot.ai")
        self.assertEqual(data["role"], "authenticated")
        self.assertFalse(data["is_guest"])

    def test_es256_select_correct_key_by_kid(self):
        """Selects the correct public key from JWKS when multiple keys exist using JWT kid header."""
        user_uuid = "c3d4e5f6-a7b8-9012-cdef-123456789012"
        # Sign with secondary EC key
        token = self._create_es256_token(
            sub=user_uuid,
            kid=self.ec_second_kid,
            key=self.ec_second_private_key,
        )
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user_id"], user_uuid)

    def test_es256_invalid_signature_rejected(self):
        """ES256 token signed with unauthorized private key is rejected with 401 INVALID_SIGNATURE."""
        token = self._create_es256_token(
            kid=self.ec_kid,
            key=self.ec_other_private_key,  # Wrong key
        )
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_SIGNATURE")

    def test_es256_expired_token_rejected(self):
        """ES256 token with exp in the past is rejected with 401 TOKEN_EXPIRED."""
        token = self._create_es256_token(exp_offset=-3600)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "TOKEN_EXPIRED")

    def test_es256_wrong_audience_rejected(self):
        """ES256 token with mismatched audience is rejected with 401 INVALID_AUDIENCE."""
        token = self._create_es256_token(aud="unrecognized_audience")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_AUDIENCE")

    def test_es256_unknown_kid_rejected(self):
        """ES256 token with unknown kid header is rejected with 401 UNKNOWN_KID."""
        token = self._create_es256_token(kid="nonexistent-key-id-999")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNKNOWN_KID")

    def test_es256_missing_kid_rejected(self):
        """ES256 token missing kid header when verifying against JWKS is rejected with 401 INVALID_TOKEN."""
        token = self._create_es256_token(kid=None)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_TOKEN")
        self.assertIn("missing required key ID", data["error"]["message"])

    def test_es256_valid_issuer_accepted(self):
        """ES256 token with matching issuer succeeds when issuer enforcement is active."""
        expected_issuer = "https://myproject.supabase.co/auth/v1"
        self.app.config["SUPABASE_JWT_ISSUER"] = expected_issuer
        token = self._create_es256_token(iss=expected_issuer)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)

    def test_es256_invalid_issuer_rejected(self):
        """ES256 token with mismatched issuer is rejected with 401 INVALID_ISSUER."""
        self.app.config["SUPABASE_JWT_ISSUER"] = "https://myproject.supabase.co/auth/v1"
        token = self._create_es256_token(iss="https://impostor.supabase.co/auth/v1")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_ISSUER")

    def test_es256_missing_sub_rejected(self):
        """ES256 token missing sub claim is rejected with 401 INVALID_TOKEN."""
        payload = {
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, self.ec_private_key, algorithm="ES256", headers={"kid": self.ec_kid})
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_TOKEN")

    def test_unsupported_algorithm_rejected(self):
        """Token with unsupported algorithm or 'none' is rejected with 401 INVALID_ALGORITHM."""
        # Algorithm: none
        payload = {
            "sub": str(uuid.uuid4()),
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        }
        token_none = jwt.encode(payload, key="", algorithm="none")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token_none}"},
        )
        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "INVALID_ALGORITHM")

    def test_service_role_key_never_used_for_jwt_verification(self):
        """Verifies that SUPABASE_SERVICE_ROLE_KEY is NEVER used for JWT signature verification."""
        service_role_key = "dummy-service-role-key-for-admin-never-jwt-secret"
        self.app.config["SUPABASE_SERVICE_ROLE_KEY"] = service_role_key

        # Token signed with service role key must fail signature verification against SUPABASE_JWT_SECRET
        bad_token = self._create_token(secret=service_role_key)
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_SIGNATURE")

        # When SUPABASE_JWT_SECRET is empty, system fails closed with 500 CONFIGURATION_ERROR
        # and never falls back to SUPABASE_SERVICE_ROLE_KEY
        self.app.config["SUPABASE_JWT_SECRET"] = ""
        response_unconfigured = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {bad_token}"},
        )
        self.assertEqual(response_unconfigured.status_code, 500)
        self.assertEqual(response_unconfigured.get_json()["error"]["code"], "CONFIGURATION_ERROR")

    def test_jwks_connection_error_mapped_to_503(self):
        """When JWKS client fails to connect to endpoint, returns 503 SERVICE_UNAVAILABLE."""
        # Configure a mock JWKS client that raises PyJWKClientConnectionError
        mock_jwks_client = MagicMock()
        mock_jwks_client.get_signing_key.side_effect = PyJWKClientConnectionError("Connection timed out")
        self.app.config["JWKS_DATA"] = None
        self.app.config["JWKS_CLIENT"] = mock_jwks_client

        token = self._create_es256_token(kid="any-kid")
        response = self.client.get(
            "/api/test/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "SERVICE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
