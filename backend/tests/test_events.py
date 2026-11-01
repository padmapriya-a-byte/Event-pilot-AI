"""EventPilot AI - Automated Test Suite for Events & Preferences API.

Tests Event CRUD endpoints, preferences endpoints, input validation against schema
constraints, ownership isolation, fail-closed database handling, and error mapping.
"""

import os
import sys
import time
import uuid
import unittest
from typing import Dict, Any, List, Optional
import jwt

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app
from app.config import Config
from app.services.event_service import EventService
from app.utils.errors import APIError


class TestConfig(Config):
    """Test configuration overriding base settings."""
    TESTING = True
    ENV = "testing"
    SECRET_KEY = "test-secret-key-for-unit-testing"
    SUPABASE_JWT_SECRET = "super-secret-jwt-signing-key-for-testing-at-least-32-chars"
    SUPABASE_JWT_ALGORITHM = "HS256"
    SUPABASE_JWT_AUDIENCE = "authenticated"
    SUPABASE_JWT_ISSUER = None
    SUPABASE_JWT_PUBLIC_KEY = None


class MockQueryBuilder:
    """In-memory Postgrest-like query builder simulating Supabase table operations."""

    def __init__(self, table_name: str, storage: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.storage = storage
        self._filters = []
        self._order_by = None
        self._order_desc = False
        self._range_start = 0
        self._range_end = None
        self._action = "select"
        self._action_data = None

    def select(self, columns: str = "*"):
        self._action = "select"
        return self

    def insert(self, data: Any):
        self._action = "insert"
        self._action_data = data
        return self

    def update(self, data: Any):
        self._action = "update"
        self._action_data = data
        return self

    def delete(self):
        self._action = "delete"
        return self

    def eq(self, column: str, value: Any):
        self._filters.append((column, value))
        return self

    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._range_start = start
        self._range_end = end
        return self

    def execute(self):
        rows = self.storage.get(self.table_name, [])

        if self._action == "insert":
            inserted_list = []
            records = self._action_data if isinstance(self._action_data, list) else [self._action_data]
            for record in records:
                new_row = dict(record)
                if "id" not in new_row:
                    new_row["id"] = str(uuid.uuid4())
                if "created_at" not in new_row:
                    new_row["created_at"] = "2026-10-25T00:00:00Z"
                if "updated_at" not in new_row:
                    new_row["updated_at"] = "2026-10-25T00:00:00Z"
                rows.append(new_row)
                inserted_list.append(new_row)
            return type("APIResponse", (), {"data": inserted_list})()

        # Filter rows
        filtered = []
        for row in rows:
            matches = True
            for col, val in self._filters:
                if row.get(col) != val:
                    matches = False
                    break
            if matches:
                filtered.append(row)

        if self._action == "select":
            result = list(filtered)
            if self._order_by:
                result.sort(key=lambda r: r.get(self._order_by, ""), reverse=self._order_desc)
            if self._range_end is not None:
                result = result[self._range_start : self._range_end + 1]
            return type("APIResponse", (), {"data": [dict(r) for r in result]})()

        elif self._action == "update":
            updated_list = []
            for row in filtered:
                row.update(self._action_data)
                row["updated_at"] = "2026-10-25T00:01:00Z"
                updated_list.append(dict(row))
            return type("APIResponse", (), {"data": updated_list})()

        elif self._action == "delete":
            deleted_list = []
            remaining = []
            for row in rows:
                matches = True
                for col, val in self._filters:
                    if row.get(col) != val:
                        matches = False
                        break
                if matches:
                    deleted_list.append(dict(row))
                else:
                    remaining.append(row)
            self.storage[self.table_name] = remaining
            return type("APIResponse", (), {"data": deleted_list})()


class MockSupabaseClient:
    """Mock Supabase client providing .table() access to simulated storage."""

    def __init__(self):
        self.storage: Dict[str, List[Dict[str, Any]]] = {
            "events": [],
            "event_preferences": [],
        }

    def table(self, table_name: str) -> MockQueryBuilder:
        return MockQueryBuilder(table_name, self.storage)


class MockAdminService:
    """Mock SupabaseAdminService providing a mock client."""

    def __init__(self, client: Optional[MockSupabaseClient] = None, is_configured: bool = True):
        self._client = client or MockSupabaseClient()
        self._is_configured = is_configured

    @property
    def client(self) -> MockSupabaseClient:
        if not self._is_configured:
            raise APIError("Supabase admin service is not configured.", status_code=503, code="SERVICE_UNAVAILABLE")
        return self._client

    @property
    def is_configured(self) -> bool:
        return self._is_configured


class EventsTestCase(unittest.TestCase):
    """Test suite for Event API endpoints, preferences, and ownership isolation."""

    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        # Initialize mock Supabase client and service
        self.mock_supabase = MockSupabaseClient()
        self.mock_admin_service = MockAdminService(self.mock_supabase)
        self.event_service = EventService(self.mock_admin_service)

        # Wire event service and ownership resolver to mock data
        self.app.config["EVENT_SERVICE"] = self.event_service

        def mock_event_resolver(event_id: str):
            res = self.mock_supabase.table("events").select("*").eq("id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None

        self.app.config["EVENT_RESOLVER"] = mock_event_resolver

        # Default test user identities
        self.user_a_id = "11111111-1111-1111-1111-111111111111"
        self.user_b_id = "22222222-2222-2222-2222-222222222222"

        self.token_user_a = self._generate_token(self.user_a_id, "user_a@eventpilot.ai")
        self.token_user_b = self._generate_token(self.user_b_id, "user_b@eventpilot.ai")

    def _generate_token(self, user_id: str, email: str = "user@eventpilot.ai") -> str:
        """Helper to create a signed JWT for testing."""
        payload = {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, TestConfig.SUPABASE_JWT_SECRET, algorithm="HS256")

    # =========================================================================
    # 1. Event Creation Tests (POST /api/events)
    # =========================================================================

    def test_create_event_success(self):
        """User A can create a valid event with default fields populated."""
        payload = {
            "title": "Global AI Summit 2026",
            "event_type": "conference",
            "description": "Annual AI conference for researchers and engineers.",
            "start_date": "2026-11-10T09:00:00Z",
            "end_date": "2026-11-12T18:00:00Z",
            "timezone": "America/New_York",
            "expected_attendees": 500,
            "currency": "USD",
            "target_budget": 50000.0,
        }

        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data["success"])
        created = data["data"]
        self.assertEqual(created["title"], "Global AI Summit 2026")
        self.assertEqual(created["event_type"], "conference")
        self.assertEqual(created["owner_id"], self.user_a_id)
        self.assertEqual(created["status"], "draft")
        self.assertFalse(created["is_archived"])
        self.assertEqual(created["currency"], "USD")
        self.assertEqual(created["expected_attendees"], 500)

        # Verify event preferences record was auto-initialized
        pref_res = self.mock_supabase.table("event_preferences").select("*").eq("event_id", created["id"]).execute()
        self.assertEqual(len(pref_res.data), 1)

    def test_create_event_ignores_client_supplied_owner_id(self):
        """Client supplying a spoofed owner_id in request body is ignored; event is assigned to token sub."""
        payload = {
            "title": "Unauthorized Takeover Attempt",
            "event_type": "corporate",
            "owner_id": self.user_b_id,  # Spoofed owner
        }

        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        created = response.get_json()["data"]
        # Owner must be User A (from verified token), NOT User B
        self.assertEqual(created["owner_id"], self.user_a_id)
        self.assertNotEqual(created["owner_id"], self.user_b_id)

    def test_create_event_unauthenticated_rejected(self):
        """Unauthenticated request to create event returns 401."""
        response = self.client.post(
            "/api/events",
            json={"title": "Private Event", "event_type": "meetup"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "UNAUTHORIZED")

    def test_create_event_non_json_body_rejected(self):
        """Non-JSON payload returns 400 BAD_REQUEST."""
        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            data="not json string",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "BAD_REQUEST")

    def test_create_event_missing_or_short_title(self):
        """Event with missing or < 2 char title returns 400 VALIDATION_ERROR."""
        # Missing title
        res1 = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"event_type": "conference"},
        )
        self.assertEqual(res1.status_code, 400)
        self.assertEqual(res1.get_json()["error"]["code"], "VALIDATION_ERROR")

        # Title too short (< 2 chars after strip)
        res2 = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": " X ", "event_type": "conference"},
        )
        self.assertEqual(res2.status_code, 400)
        self.assertEqual(res2.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_create_event_invalid_event_type(self):
        """Invalid event_type returns 400 VALIDATION_ERROR."""
        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Valid Title", "event_type": "unrecognized_type"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_create_event_invalid_date_range(self):
        """end_date earlier than start_date returns 400 VALIDATION_ERROR."""
        payload = {
            "title": "Time Traveler Convention",
            "event_type": "meetup",
            "start_date": "2026-12-01T10:00:00Z",
            "end_date": "2026-11-30T10:00:00Z",  # Earlier than start
        }
        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("cannot be earlier", data["error"]["message"])

    def test_create_event_invalid_attendees_or_budget(self):
        """Negative attendees or target budget returns 400 VALIDATION_ERROR."""
        # Negative attendees
        res1 = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Tech Talk", "event_type": "meetup", "expected_attendees": -5},
        )
        self.assertEqual(res1.status_code, 400)

        # Negative budget
        res2 = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Tech Talk", "event_type": "meetup", "target_budget": -100.0},
        )
        self.assertEqual(res2.status_code, 400)

    def test_create_event_invalid_currency(self):
        """Non 3-letter uppercase currency returns 400 VALIDATION_ERROR."""
        for invalid_curr in ["usd", "US", "USDD", "123"]:
            res = self.client.post(
                "/api/events",
                headers={"Authorization": f"Bearer {self.token_user_a}"},
                json={"title": "Tech Talk", "event_type": "meetup", "currency": invalid_curr},
            )
            self.assertEqual(res.status_code, 400)

    # =========================================================================
    # 2. Event Listing Tests (GET /api/events) - Ownership Isolation
    # =========================================================================

    def test_list_events_ownership_isolation(self):
        """User A sees only their events; User B sees only their own events."""
        # Create 2 events for User A
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Event 1", "event_type": "conference"},
        )
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Event 2", "event_type": "hackathon"},
        )

        # Create 1 event for User B
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"title": "User B Secret Meeting", "event_type": "corporate"},
        )

        # Query as User A
        res_a = self.client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(res_a.status_code, 200)
        events_a = res_a.get_json()["data"]
        self.assertEqual(len(events_a), 2)
        for ev in events_a:
            self.assertEqual(ev["owner_id"], self.user_a_id)
            self.assertNotEqual(ev["owner_id"], self.user_b_id)

        # Query as User B
        res_b = self.client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(res_b.status_code, 200)
        events_b = res_b.get_json()["data"]
        self.assertEqual(len(events_b), 1)
        self.assertEqual(events_b[0]["title"], "User B Secret Meeting")
        self.assertEqual(events_b[0]["owner_id"], self.user_b_id)

    def test_list_events_filtering_status_and_archived(self):
        """List events supports status filtering and excludes archived by default."""
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Planning Event", "event_type": "wedding", "status": "planning"},
        )
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Draft Event", "event_type": "meetup", "status": "draft"},
        )
        self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Archived Event", "event_type": "concert", "is_archived": True},
        )

        # Default query (archived excluded)
        res_default = self.client.get(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        data_default = res_default.get_json()["data"]
        self.assertEqual(len(data_default), 2)
        titles = [e["title"] for e in data_default]
        self.assertNotIn("Archived Event", titles)

        # Include archived
        res_archived = self.client.get(
            "/api/events?include_archived=true",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        data_archived = res_archived.get_json()["data"]
        self.assertEqual(len(data_archived), 3)

        # Filter by status=planning
        res_status = self.client.get(
            "/api/events?status=planning",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        data_status = res_status.get_json()["data"]
        self.assertEqual(len(data_status), 1)
        self.assertEqual(data_status[0]["title"], "Planning Event")

    # =========================================================================
    # 3. Event Retrieval Tests (GET /api/events/<event_id>)
    # =========================================================================

    def test_get_event_by_id_owner_success(self):
        """Owner can retrieve their event by UUID."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Developer Meetup", "event_type": "meetup"},
        )
        event_id = create_res.get_json()["data"]["id"]

        get_res = self.client.get(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(get_res.status_code, 200)
        data = get_res.get_json()["data"]
        self.assertEqual(data["id"], event_id)
        self.assertEqual(data["title"], "Developer Meetup")

    def test_get_event_by_id_other_user_forbidden(self):
        """User B cannot access User A's event (returns 403 FORBIDDEN)."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Private Event", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        get_res = self.client.get(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(get_res.status_code, 403)
        self.assertEqual(get_res.get_json()["error"]["code"], "FORBIDDEN")

    def test_get_event_by_id_not_found(self):
        """Non-existent UUID returns 404 NOT_FOUND."""
        non_existent_id = str(uuid.uuid4())
        response = self.client.get(
            f"/api/events/{non_existent_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "NOT_FOUND")

    # =========================================================================
    # 4. Event Update Tests (PATCH /api/events/<event_id>)
    # =========================================================================

    def test_patch_event_success(self):
        """Owner can update allowed event fields."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Initial Title", "event_type": "exhibition", "expected_attendees": 50},
        )
        event_id = create_res.get_json()["data"]["id"]

        patch_payload = {
            "title": "Updated Title",
            "status": "planning",
            "expected_attendees": 150,
            "target_budget": 12000.50,
            "owner_id": self.user_b_id,  # Should be ignored
        }

        patch_res = self.client.patch(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=patch_payload,
        )
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.get_json()["data"]
        self.assertEqual(data["title"], "Updated Title")
        self.assertEqual(data["status"], "planning")
        self.assertEqual(data["expected_attendees"], 150)
        self.assertEqual(data["target_budget"], 12000.50)
        self.assertEqual(data["owner_id"], self.user_a_id)

    def test_patch_event_invalid_date_order(self):
        """Updating end_date earlier than existing start_date returns 400."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Date Order Test",
                "event_type": "conference",
                "start_date": "2026-11-10T10:00:00Z",
                "end_date": "2026-11-12T10:00:00Z",
            },
        )
        event_id = create_res.get_json()["data"]["id"]

        patch_res = self.client.patch(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"end_date": "2026-11-05T10:00:00Z"},  # Earlier than 2026-11-10
        )
        self.assertEqual(patch_res.status_code, 400)
        self.assertEqual(patch_res.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_patch_event_other_user_forbidden(self):
        """User B cannot update User A's event."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Event", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        patch_res = self.client.patch(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"title": "Hacked Title"},
        )
        self.assertEqual(patch_res.status_code, 403)
        self.assertEqual(patch_res.get_json()["error"]["code"], "FORBIDDEN")

    # =========================================================================
    # 5. Event Deletion Tests (DELETE /api/events/<event_id>)
    # =========================================================================

    def test_delete_event_success(self):
        """Owner can delete their event."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Temporary Event", "event_type": "meetup"},
        )
        event_id = create_res.get_json()["data"]["id"]

        del_res = self.client.delete(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

        # Subsequent fetch returns 404
        get_res = self.client.get(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(get_res.status_code, 404)

    def test_delete_event_other_user_forbidden(self):
        """User B cannot delete User A's event."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Event", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        del_res = self.client.delete(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(del_res.status_code, 403)
        self.assertEqual(del_res.get_json()["error"]["code"], "FORBIDDEN")

    # =========================================================================
    # 6. Event Preferences Tests (/api/events/<event_id>/preferences)
    # =========================================================================

    def test_get_preferences_success(self):
        """Owner can retrieve preferences for their event."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Preferences Test", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        pref_res = self.client.get(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(pref_res.status_code, 200)
        data = pref_res.get_json()["data"]
        self.assertEqual(data["event_id"], event_id)
        self.assertIn("vibe_style", data)
        self.assertIn("ai_generation_parameters", data)

    def test_update_preferences_success(self):
        """Owner can update structured event preferences."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Preferences Update Test", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        update_payload = {
            "vibe_style": ["modern", "minimalist", "energetic"],
            "catering_preferences": {
                "vegan_options": True,
                "gluten_free": True,
                "budget_per_person": 35.0,
            },
            "accessibility_requirements": ["wheelchair_access", "asl_interpreter"],
            "target_audience": "Tech startups and venture capitalists",
            "ai_generation_parameters": {
                "temperature": 0.8,
                "model": "gemini-2.5-flash",
            },
            "custom_constraints": [
                {"rule": "no_single_use_plastics", "priority": "high"},
            ],
        }

        put_res = self.client.put(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=update_payload,
        )
        self.assertEqual(put_res.status_code, 200)
        data = put_res.get_json()["data"]
        self.assertEqual(data["vibe_style"], ["modern", "minimalist", "energetic"])
        self.assertEqual(data["target_audience"], "Tech startups and venture capitalists")
        self.assertTrue(data["catering_preferences"]["vegan_options"])

    def test_preferences_validation_errors(self):
        """Preferences endpoint rejects invalid formats with 400 VALIDATION_ERROR."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Preferences Validation Test", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        # vibe_style must be a list of strings
        res1 = self.client.put(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"vibe_style": "not-a-list"},
        )
        self.assertEqual(res1.status_code, 400)

        # catering_preferences must be a dict
        res2 = self.client.put(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"catering_preferences": ["not-a-dict"]},
        )
        self.assertEqual(res2.status_code, 400)

    def test_preferences_other_user_forbidden(self):
        """User B cannot read or update User A's event preferences."""
        create_res = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "User A Event", "event_type": "conference"},
        )
        event_id = create_res.get_json()["data"]["id"]

        # User B reads User A's preferences -> 403
        get_res = self.client.get(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(get_res.status_code, 403)

        # User B updates User A's preferences -> 403
        put_res = self.client.put(
            f"/api/events/{event_id}/preferences",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"vibe_style": ["hacked"]},
        )
        self.assertEqual(put_res.status_code, 403)

    # =========================================================================
    # 7. Database Fail-Closed & Error Handling Tests
    # =========================================================================

    def test_database_service_unconfigured_fails_closed(self):
        """When Supabase is unconfigured, operations return 503 SERVICE_UNAVAILABLE without leaking details."""
        unconfigured_service = MockAdminService(is_configured=False)
        svc = EventService(unconfigured_service)
        self.app.config["EVENT_SERVICE"] = svc

        response = self.client.post(
            "/api/events",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Service Check", "event_type": "conference"},
        )
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "SERVICE_UNAVAILABLE")

    def test_event_resolver_infrastructure_failure_fails_closed(self):
        """When event ownership resolver encounters a database error, access is denied (503)."""
        def broken_resolver(event_id: str):
            raise RuntimeError("Database connection timed out")

        self.app.config["EVENT_RESOLVER"] = broken_resolver
        event_id = str(uuid.uuid4())

        response = self.client.get(
            f"/api/events/{event_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "SERVICE_UNAVAILABLE")
        self.assertNotIn("RuntimeError", data["error"]["message"])


if __name__ == "__main__":
    unittest.main()
