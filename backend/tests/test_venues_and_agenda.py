"""EventPilot AI - Automated Test Suite for Venues and Agenda Sessions.

Tests:
  - Venue CRUD operations and ownership isolation.
  - Venue constraints: positive capacity, non-negative rental cost, allowed statuses.
  - Single selected venue invariant (at most one selected venue per event).
  - Agenda session CRUD operations and ownership isolation.
  - Agenda constraints: end_time strictly greater than start_time, allowed session types.
  - Composite boundary check: agenda session cannot reference venue from another event.
"""

import os
import sys
import time
import uuid
import threading
import unittest
from typing import Dict, Any, List, Optional
import jwt

# Ensure backend directory is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app
from app.config import Config
from app.services.venue_service import VenueService
from app.utils.errors import APIError


class TestConfig(Config):
    TESTING = True
    ENV = "testing"
    SECRET_KEY = "test-secret-key-for-unit-testing"
    SUPABASE_JWT_SECRET = "super-secret-jwt-signing-key-for-testing-at-least-32-chars"
    SUPABASE_JWT_ALGORITHM = "HS256"
    SUPABASE_JWT_AUDIENCE = "authenticated"
    SUPABASE_JWT_ISSUER = None
    SUPABASE_JWT_PUBLIC_KEY = None


class MockRpcBuilder:
    """Mock Supabase RPC builder simulating stored procedures like select_event_venue."""

    def __init__(self, function_name: str, params: Dict[str, Any], storage: Dict[str, List[Dict[str, Any]]]):
        self.function_name = function_name
        self.params = params
        self.storage = storage

    def execute(self):
        if self.function_name == "select_event_venue":
            event_id = self.params.get("p_event_id")
            venue_id = self.params.get("p_venue_id")
            venues = self.storage.get("venues", [])
            target = next((v for v in venues if v.get("id") == venue_id and v.get("event_id") == event_id), None)
            if not target:
                raise Exception(f"Venue {venue_id} not found for event {event_id} (P0002)")

            # Atomically demote any currently selected venue for this event
            for v in venues:
                if v.get("event_id") == event_id and v.get("id") != venue_id:
                    v["is_selected"] = False

            # Atomically promote target venue
            target["is_selected"] = True
            target["status"] = "selected"
            return type("APIResponse", (), {"data": [dict(target)]})()

        raise RuntimeError(f"Unknown RPC function '{self.function_name}'.")


class MockQueryBuilder:
    """In-memory Postgrest-like query builder enforcing schema constraints."""

    def __init__(self, table_name: str, storage: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.storage = storage
        self._filters: List[tuple] = []
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._action = "select"
        self._action_data: Any = None

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

    def execute(self):
        rows = self.storage.get(self.table_name, [])

        if self._action == "insert":
            inserted = []
            records = self._action_data if isinstance(self._action_data, list) else [self._action_data]
            for r in records:
                row = dict(r)
                # Enforce database partial unique index idx_venues_single_selected
                if self.table_name == "venues" and row.get("is_selected") is True:
                    for existing in rows:
                        if existing.get("event_id") == row.get("event_id") and existing.get("is_selected") is True:
                            raise Exception("23505 unique constraint violation on idx_venues_single_selected")

                if "id" not in row:
                    row["id"] = str(uuid.uuid4())
                if "created_at" not in row:
                    row["created_at"] = "2026-10-25T00:00:00Z"
                if "updated_at" not in row:
                    row["updated_at"] = "2026-10-25T00:00:00Z"
                rows.append(row)
                inserted.append(dict(row))
            return type("APIResponse", (), {"data": inserted})()

        filtered = []
        for r in rows:
            matches = True
            for col, val in self._filters:
                if r.get(col) != val:
                    matches = False
                    break
            if matches:
                filtered.append(r)

        if self._action == "select":
            res = list(filtered)
            if self._order_by:
                res.sort(key=lambda x: str(x.get(self._order_by, "")), reverse=self._order_desc)
            return type("APIResponse", (), {"data": [dict(x) for x in res]})()

        elif self._action == "update":
            # Enforce database partial unique index idx_venues_single_selected on update
            if self.table_name == "venues" and self._action_data.get("is_selected") is True:
                for r in filtered:
                    target_event_id = r.get("event_id")
                    for existing in rows:
                        if (
                            existing.get("id") != r.get("id")
                            and existing.get("event_id") == target_event_id
                            and existing.get("is_selected") is True
                        ):
                            raise Exception("23505 unique constraint violation on idx_venues_single_selected")

            updated = []
            for r in filtered:
                r.update(self._action_data)
                r["updated_at"] = "2026-10-25T00:01:00Z"
                updated.append(dict(r))
            return type("APIResponse", (), {"data": updated})()

        elif self._action == "delete":
            deleted = []
            remaining = []
            for r in rows:
                matches = True
                for col, val in self._filters:
                    if r.get(col) != val:
                        matches = False
                        break
                if matches:
                    deleted.append(dict(r))
                else:
                    remaining.append(r)
            self.storage[self.table_name] = remaining
            return type("APIResponse", (), {"data": deleted})()


class MockPostgrestClient:
    """Mock PostgREST client tracking headers and auth state."""

    def __init__(self, auth_header: str = "Bearer mock-service-role-key", apikey: str = "mock-service-role-key"):
        self.headers = {"Authorization": auth_header, "apikey": apikey}

    def auth(self, token: str):
        self.headers["Authorization"] = f"Bearer {token}"
        return self


class MockSupabaseClient:
    def __init__(
        self,
        auth_header: str = "Bearer mock-service-role-key",
        apikey: str = "mock-service-role-key",
        enable_rpc: bool = True,
        parent_client: Optional["MockSupabaseClient"] = None,
    ):
        self.storage: Dict[str, List[Dict[str, Any]]] = {
            "events": [],
            "venues": [],
            "agenda_sessions": [],
        }
        self.enable_rpc = enable_rpc
        self.postgrest = MockPostgrestClient(auth_header=auth_header, apikey=apikey)
        self.user_token: Optional[str] = None
        self.parent_client = parent_client
        self.rpc_invocations: List[Dict[str, Any]] = []

    def table(self, table_name: str) -> MockQueryBuilder:
        return MockQueryBuilder(table_name, self.storage)

    def rpc(self, function_name: str, params: Dict[str, Any]) -> MockRpcBuilder:
        handler = getattr(self, "rpc_override", None) or (self.parent_client and getattr(self.parent_client, "rpc_override", None))
        if handler:
            return handler(function_name, params)
        if not self.enable_rpc:
            raise Exception(f"PGRST202 Could not find function {function_name}")
        record = {
            "function_name": function_name,
            "params": params,
            "user_token": self.user_token,
            "auth_header": self.postgrest.headers.get("Authorization"),
            "is_scoped_client": self.user_token is not None,
        }
        self.rpc_invocations.append(record)
        if self.parent_client is not None:
            self.parent_client.rpc_invocations.append(record)
        return MockRpcBuilder(function_name, params, self.storage)


class MockAdminService:
    def __init__(self, client: Optional[MockSupabaseClient] = None, is_configured: bool = True):
        self._client = client or MockSupabaseClient()
        self._is_configured = is_configured

    @property
    def client(self) -> MockSupabaseClient:
        if not self._is_configured:
            raise APIError("Supabase is not configured.", status_code=503, code="SERVICE_UNAVAILABLE")
        return self._client

    def get_user_client(self, user_token: str) -> MockSupabaseClient:
        """Returns an isolated, request-scoped client sharing storage without mutating the admin client."""
        if not self._is_configured:
            raise APIError("Supabase is not configured.", status_code=503, code="SERVICE_UNAVAILABLE")
        clean_token = user_token.replace("Bearer ", "").strip()
        scoped_client = MockSupabaseClient(
            auth_header=f"Bearer {clean_token}",
            apikey="mock-anon-key",
            enable_rpc=self._client.enable_rpc,
            parent_client=self._client,
        )
        scoped_client.storage = self._client.storage
        scoped_client.user_token = clean_token
        return scoped_client

    @property
    def is_configured(self) -> bool:
        return self._is_configured


class VenuesAndAgendaTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        self.mock_supabase = MockSupabaseClient()
        self.mock_admin_service = MockAdminService(self.mock_supabase)
        self.venue_service = VenueService(self.mock_admin_service)

        self.app.config["VENUE_SERVICE"] = self.venue_service

        def mock_event_resolver(event_id: str):
            res = self.mock_supabase.table("events").select("*").eq("id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None

        self.app.config["EVENT_RESOLVER"] = mock_event_resolver

        self.user_a_id = "11111111-1111-1111-1111-111111111111"
        self.user_b_id = "22222222-2222-2222-2222-222222222222"

        self.token_user_a = self._generate_token(self.user_a_id)
        self.token_user_b = self._generate_token(self.user_b_id)

        # Event A1
        self.event_a1_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a1_id,
            "owner_id": self.user_a_id,
            "title": "User A Summit",
            "is_archived": False,
        })

        # Event A2
        self.event_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a2_id,
            "owner_id": self.user_a_id,
            "title": "User A Workshop",
            "is_archived": False,
        })

        # Event B1 (owned by user B)
        self.event_b1_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_b1_id,
            "owner_id": self.user_b_id,
            "title": "User B Secret Gala",
            "is_archived": False,
        })

    def _generate_token(self, user_id: str) -> str:
        payload = {
            "sub": user_id,
            "email": f"{user_id}@test.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        }
        return jwt.encode(payload, TestConfig.SUPABASE_JWT_SECRET, algorithm="HS256")

    # =========================================================================
    # Venue Tests
    # =========================================================================

    def test_create_venue_success(self):
        """User A creates a venue candidate with valid data."""
        payload = {
            "name": "Grand Ballroom",
            "address": "123 Main St",
            "city": "San Francisco",
            "capacity": 300,
            "rental_cost": 4500.00,
            "amenities": ["AV Equipment", "WiFi", "Catering Kitchen"],
            "status": "shortlisted",
            "is_selected": False,
        }
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["data"]
        self.assertEqual(data["name"], "Grand Ballroom")
        self.assertEqual(data["capacity"], 300)
        self.assertEqual(data["rental_cost"], 4500.00)
        self.assertEqual(data["amenities"], ["AV Equipment", "WiFi", "Catering Kitchen"])
        self.assertFalse(data["is_selected"])
        self.assertEqual(data["event_id"], self.event_a1_id)

    def test_create_venue_single_selected_invariant(self):
        """Selecting a new venue automatically unselects the previously selected venue for the event."""
        # 1. Create Venue 1 and select it
        res1 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Venue 1", "is_selected": True},
        )
        self.assertEqual(res1.status_code, 201)
        v1_id = res1.get_json()["data"]["id"]
        self.assertTrue(res1.get_json()["data"]["is_selected"])

        # 2. Create Venue 2 and select it
        res2 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Venue 2", "is_selected": True},
        )
        self.assertEqual(res2.status_code, 201)
        self.assertTrue(res2.get_json()["data"]["is_selected"])

        # 3. Verify Venue 1 is now unselected
        get_v1 = self.client.get(
            f"/api/events/{self.event_a1_id}/venues/{v1_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(get_v1.status_code, 200)
        self.assertFalse(get_v1.get_json()["data"]["is_selected"])

    def test_create_venue_validation_errors(self):
        """Rejects empty name, non-positive capacity, negative cost, and invalid status."""
        # Empty name
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "  "},
        )
        self.assertEqual(res.status_code, 400)

        # Capacity <= 0
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Venue", "capacity": 0},
        )
        self.assertEqual(res.status_code, 400)

        # Negative rental cost
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Venue", "rental_cost": -100.00},
        )
        self.assertEqual(res.status_code, 400)

        # Invalid status
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Venue", "status": "unknown_status"},
        )
        self.assertEqual(res.status_code, 400)

    def test_venue_crud_and_cross_event_isolation(self):
        """Tests venue list, get, update, delete, and cross-event isolation."""
        # Create venue in Event A1
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Skyline Terrace", "capacity": 150},
        )
        v_id = res.get_json()["data"]["id"]

        # List venues
        list_res = self.client.get(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(len(list_res.get_json()["data"]), 1)

        # Update venue
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/venues/{v_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"rental_cost": 2500.00, "status": "proposal_received"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["data"]["rental_cost"], 2500.00)
        self.assertEqual(patch_res.get_json()["data"]["status"], "proposal_received")

        # Cross-event get (belonging to A1, queried via A2) -> 404
        cross_res = self.client.get(
            f"/api/events/{self.event_a2_id}/venues/{v_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_res.status_code, 404)

        # Delete venue
        del_res = self.client.delete(
            f"/api/events/{self.event_a1_id}/venues/{v_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

    def test_venue_ownership_isolation(self):
        """User B cannot view or modify User A's venues."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"name": "Spy Room"},
        )
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # Agenda Session Tests
    # =========================================================================

    def test_create_agenda_session_success(self):
        """Creates an agenda session with valid time range."""
        payload = {
            "title": "Keynote: Future of AI",
            "description": "Opening keynote speech",
            "speaker_facilitator": "Dr. Smith",
            "room_location": "Auditorium A",
            "start_time": "2026-11-10T09:00:00Z",
            "end_time": "2026-11-10T10:00:00Z",
            "session_type": "keynote",
            "sort_order": 1,
        }
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["data"]
        self.assertEqual(data["title"], "Keynote: Future of AI")
        self.assertEqual(data["session_type"], "keynote")
        self.assertEqual(data["event_id"], self.event_a1_id)

    def test_agenda_session_invalid_time_range_rejected(self):
        """Rejects session when end_time is earlier than or equal to start_time."""
        # end_time earlier than start_time
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Time Traveler Session",
                "start_time": "2026-11-10T11:00:00Z",
                "end_time": "2026-11-10T10:00:00Z",
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("strictly after", res.get_json()["error"]["message"])

        # end_time equal to start_time
        res2 = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Zero Duration Session",
                "start_time": "2026-11-10T10:00:00Z",
                "end_time": "2026-11-10T10:00:00Z",
            },
        )
        self.assertEqual(res2.status_code, 400)

    def test_agenda_session_cross_event_venue_boundary_enforcement(self):
        """Rejects agenda session referencing a venue belonging to another event."""
        # 1. Create Venue belonging to Event A2
        res_v = self.client.post(
            f"/api/events/{self.event_a2_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Event A2 Conference Room"},
        )
        v_a2_id = res_v.get_json()["data"]["id"]

        # 2. Attempt to create Agenda Session in Event A1 referencing Event A2's venue
        res_session = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Cross-Event Session",
                "start_time": "2026-11-10T09:00:00Z",
                "end_time": "2026-11-10T10:00:00Z",
                "venue_id": v_a2_id,
            },
        )
        self.assertEqual(res_session.status_code, 400)
        self.assertEqual(res_session.get_json()["error"]["code"], "CROSS_EVENT_REFERENCE_FORBIDDEN")

    def test_agenda_session_valid_venue_reference(self):
        """Allows agenda session referencing a venue belonging to the SAME event."""
        # Create venue in Event A1
        res_v = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Event A1 Main Stage"},
        )
        v_a1_id = res_v.get_json()["data"]["id"]

        # Create session in Event A1 referencing the venue
        res_session = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Valid Venue Session",
                "start_time": "2026-11-10T09:00:00Z",
                "end_time": "2026-11-10T10:00:00Z",
                "venue_id": v_a1_id,
            },
        )
        self.assertEqual(res_session.status_code, 201)
        self.assertEqual(res_session.get_json()["data"]["venue_id"], v_a1_id)

    def test_agenda_crud_and_cross_event_isolation(self):
        """Tests agenda session list, get, update, delete, and cross-event isolation."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/agenda",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Panel Discussion",
                "start_time": "2026-11-10T14:00:00Z",
                "end_time": "2026-11-10T15:00:00Z",
                "session_type": "panel",
            },
        )
        s_id = res.get_json()["data"]["id"]

        # Update
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/agenda/{s_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Updated Panel Discussion", "sort_order": 5},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["data"]["title"], "Updated Panel Discussion")

        # Cross-event get -> 404
        cross_res = self.client.get(
            f"/api/events/{self.event_a2_id}/agenda/{s_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_res.status_code, 404)

        # Delete
        del_res = self.client.delete(
            f"/api/events/{self.event_a1_id}/agenda/{s_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

    # =========================================================================
    # 5. Venue Selection Concurrency and Invariant Enforcement Tests
    # =========================================================================

    def test_concurrent_venue_selection_single_selected_invariant(self):
        """Concurrent PATCH requests selecting different venues for the same event leave exactly one selected."""
        # 1. Create 4 shortlisted venues
        venue_ids = []
        for i in range(4):
            res = self.client.post(
                f"/api/events/{self.event_a1_id}/venues",
                headers={"Authorization": f"Bearer {self.token_user_a}"},
                json={"name": f"Candidate Venue {i+1}", "is_selected": False},
            )
            self.assertEqual(res.status_code, 201)
            venue_ids.append(res.get_json()["data"]["id"])

        # 2. Concurrently select different venues from separate threads
        thread_results = {}
        thread_errors = []

        def worker(v_id: str, thread_idx: int):
            try:
                # Use a separate test client session if needed
                patch_res = self.client.patch(
                    f"/api/events/{self.event_a1_id}/venues/{v_id}",
                    headers={"Authorization": f"Bearer {self.token_user_a}"},
                    json={"is_selected": True},
                )
                thread_results[thread_idx] = patch_res.status_code
            except Exception as e:
                thread_errors.append(f"Thread {thread_idx} raised {str(e)}")

        threads = [threading.Thread(target=worker, args=(v_id, idx)) for idx, v_id in enumerate(venue_ids)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(thread_errors, [], f"Thread errors occurred during concurrent selection: {thread_errors}")
        for idx in range(4):
            self.assertEqual(thread_results[idx], 200, f"Thread {idx} did not return 200: {thread_results}")

        # 3. Verify database invariant: exactly ONE venue remains selected
        all_venues = [v for v in self.mock_supabase.storage["venues"] if v.get("event_id") == self.event_a1_id]
        selected_venues = [v for v in all_venues if v.get("is_selected") is True]
        self.assertEqual(
            len(selected_venues),
            1,
            f"Expected exactly 1 selected venue, found {len(selected_venues)}: {selected_venues}",
        )

    def test_concurrent_venue_creation_with_selection(self):
        """Concurrent POST requests creating venues with is_selected=True leave exactly one selected."""
        thread_results = {}
        thread_errors = []

        def worker(idx: int):
            try:
                res = self.client.post(
                    f"/api/events/{self.event_a1_id}/venues",
                    headers={"Authorization": f"Bearer {self.token_user_a}"},
                    json={"name": f"Concurrent New Venue {idx}", "is_selected": True},
                )
                thread_results[idx] = res.status_code
            except Exception as e:
                thread_errors.append(f"Thread {idx} raised {str(e)}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(thread_errors, [], f"Thread errors occurred during concurrent creation: {thread_errors}")
        for idx in range(4):
            self.assertEqual(thread_results[idx], 201, f"Thread {idx} did not return 201: {thread_results}")

        # Verify only one venue is selected
        all_venues = [v for v in self.mock_supabase.storage["venues"] if v.get("event_id") == self.event_a1_id]
        selected_venues = [v for v in all_venues if v.get("is_selected") is True]
        self.assertEqual(
            len(selected_venues),
            1,
            f"Expected exactly 1 selected venue, found {len(selected_venues)}",
        )

    def test_database_partial_unique_index_enforcement(self):
        """Simulated database raises 23505 if two venues are selected without unselecting."""
        # Insert venue 1 as selected
        self.mock_supabase.table("venues").insert({
            "event_id": self.event_a1_id,
            "name": "Direct Venue 1",
            "is_selected": True,
        }).execute()

        # Attempt to insert venue 2 as selected directly without unselecting venue 1
        with self.assertRaises(Exception) as cm:
            self.mock_supabase.table("venues").insert({
                "event_id": self.event_a1_id,
                "name": "Direct Venue 2",
                "is_selected": True,
            }).execute()
        self.assertIn("23505", str(cm.exception))
        self.assertIn("idx_venues_single_selected", str(cm.exception))

    def test_atomic_rpc_selection_flow(self):
        """Atomic RPC select_event_venue demotes existing venue and selects target venue."""
        v1 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "RPC Venue 1", "is_selected": True},
        ).get_json()["data"]

        v2 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "RPC Venue 2", "is_selected": False},
        ).get_json()["data"]

        # Call RPC directly
        rpc_res = self.mock_supabase.rpc("select_event_venue", {
            "p_event_id": self.event_a1_id,
            "p_venue_id": v2["id"],
        }).execute()

        self.assertTrue(rpc_res.data[0]["is_selected"])
        self.assertEqual(rpc_res.data[0]["status"], "selected")

        # Verify v1 is demoted in storage
        v1_record = next(v for v in self.mock_supabase.storage["venues"] if v["id"] == v1["id"])
        self.assertFalse(v1_record["is_selected"])

    # =========================================================================
    # 6. Request-Scoped Supabase Client & Concurrency Isolation Tests
    # =========================================================================

    def test_venue_selection_rpc_invoked_via_user_scoped_client(self):
        """PATCH /venues/<venue_id> with is_selected=True invokes select_event_venue via user-scoped client."""
        # 1. Create candidate venue
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Scope Test Venue", "is_selected": False},
        )
        self.assertEqual(res.status_code, 201)
        v_id = res.get_json()["data"]["id"]

        # Clear prior RPC invocations from setup
        self.mock_supabase.rpc_invocations.clear()

        # 2. Select venue via PATCH endpoint
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/venues/{v_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"is_selected": True},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertTrue(patch_res.get_json()["data"]["is_selected"])

        # 3. Assert select_event_venue RPC was called exactly on a user-scoped client
        self.assertEqual(len(self.mock_supabase.rpc_invocations), 1)
        rpc_call = self.mock_supabase.rpc_invocations[0]
        self.assertEqual(rpc_call["function_name"], "select_event_venue")
        self.assertEqual(rpc_call["params"], {"p_event_id": self.event_a1_id, "p_venue_id": v_id})
        self.assertTrue(rpc_call["is_scoped_client"])
        self.assertEqual(rpc_call["user_token"], self.token_user_a)
        self.assertEqual(rpc_call["auth_header"], f"Bearer {self.token_user_a}")

        # 4. Assert shared admin client was NOT mutated
        admin_client = self.mock_admin_service.client
        self.assertEqual(admin_client.postgrest.headers.get("Authorization"), "Bearer mock-service-role-key")
        self.assertIsNone(admin_client.user_token)

    def test_venue_selection_direct_service_with_user_token(self):
        """Direct VenueService.update_venue with user_token calls RPC with scoped auth and preserves admin client."""
        v = self.venue_service.create_venue(self.event_a1_id, {"name": "Direct Test Venue", "is_selected": False})
        v_id = v["id"]

        self.mock_supabase.rpc_invocations.clear()
        updated = self.venue_service.update_venue(
            self.event_a1_id,
            v_id,
            {"is_selected": True},
            user_token=self.token_user_a,
        )
        self.assertTrue(updated["is_selected"])

        # RPC was called with user token
        self.assertEqual(len(self.mock_supabase.rpc_invocations), 1)
        rpc_call = self.mock_supabase.rpc_invocations[0]
        self.assertEqual(rpc_call["auth_header"], f"Bearer {self.token_user_a}")

        # Admin client remains pristine
        self.assertEqual(self.mock_admin_service.client.postgrest.headers.get("Authorization"), "Bearer mock-service-role-key")

    def test_venue_selection_fallback_when_rpc_unavailable(self):
        """When RPC fails or is unavailable, update_venue safely falls back to synchronized table update."""
        # Disable RPC
        self.mock_supabase.enable_rpc = False

        res1 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Fallback Venue 1", "is_selected": True},
        )
        v1_id = res1.get_json()["data"]["id"]

        res2 = self.client.post(
            f"/api/events/{self.event_a1_id}/venues",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Fallback Venue 2", "is_selected": False},
        )
        v2_id = res2.get_json()["data"]["id"]

        # Select Venue 2
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/venues/{v2_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"is_selected": True},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertTrue(patch_res.get_json()["data"]["is_selected"])

        # Check in storage that v1 was demoted and v2 is selected
        v1_data = next(v for v in self.mock_supabase.storage["venues"] if v["id"] == v1_id)
        v2_data = next(v for v in self.mock_supabase.storage["venues"] if v["id"] == v2_id)
        self.assertFalse(v1_data["is_selected"])
        self.assertTrue(v2_data["is_selected"])

    def test_venue_selection_preserves_admin_client_for_table_operations(self):
        """Non-selection updates (e.g. capacity or cost changes) use standard table update and do not invoke RPC."""
        v = self.venue_service.create_venue(self.event_a1_id, {"name": "Standard Edit Venue", "capacity": 100})
        v_id = v["id"]

        self.mock_supabase.rpc_invocations.clear()
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/venues/{v_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"capacity": 250, "rental_cost": 1500.00},
        )
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.get_json()["data"]
        self.assertEqual(data["capacity"], 250)
        self.assertEqual(data["rental_cost"], 1500.00)

        # No RPC was triggered
        self.assertEqual(len(self.mock_supabase.rpc_invocations), 0)
        self.assertEqual(self.mock_admin_service.client.postgrest.headers.get("Authorization"), "Bearer mock-service-role-key")

    def test_concurrent_venue_selection_user_token_isolation(self):
        """Concurrent selection calls from different users use isolated tokens and never mutate admin client."""
        # Create venue in A1 and venue in A2
        v_a1 = self.venue_service.create_venue(self.event_a1_id, {"name": "Venue A1", "is_selected": False})
        v_a2 = self.venue_service.create_venue(self.event_a2_id, {"name": "Venue A2", "is_selected": False})

        token_custom_1 = "custom-jwt-token-alpha"
        token_custom_2 = "custom-jwt-token-beta"

        thread_errors = []

        def worker(event_id: str, venue_id: str, token: str):
            try:
                for _ in range(5):
                    updated = self.venue_service.update_venue(
                        event_id,
                        venue_id,
                        {"is_selected": True},
                        user_token=token,
                    )
                    if not updated.get("is_selected"):
                        thread_errors.append(f"Venue {venue_id} not selected")
                    # Verify admin client untouched
                    auth = self.mock_admin_service.client.postgrest.headers.get("Authorization")
                    if auth != "Bearer mock-service-role-key":
                        thread_errors.append(f"Admin client mutated to: {auth}")
            except Exception as e:
                thread_errors.append(str(e))

        t1 = threading.Thread(target=worker, args=(self.event_a1_id, v_a1["id"], token_custom_1))
        t2 = threading.Thread(target=worker, args=(self.event_a2_id, v_a2["id"], token_custom_2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(thread_errors, [])
        self.assertEqual(self.mock_admin_service.client.postgrest.headers.get("Authorization"), "Bearer mock-service-role-key")

    def test_venue_selection_rpc_forbidden_raises_403(self):
        """When select_event_venue RPC raises 42501 caller does not own event, update_venue maps to 403 FORBIDDEN."""
        v = self.venue_service.create_venue(self.event_a1_id, {"name": "Forbidden Venue", "is_selected": False})
        v_id = v["id"]

        # Override rpc on user-scoped client or mock supabase to simulate PostgreSQL 42501 ownership failure
        def mock_forbidden_rpc(function_name: str, params: Dict[str, Any]):
            raise Exception("42501: Forbidden: Caller does not own event")

        self.mock_supabase.rpc_override = mock_forbidden_rpc

        with self.assertRaises(APIError) as cm:
            self.venue_service.update_venue(
                self.event_a1_id,
                v_id,
                {"is_selected": True},
                user_token=self.token_user_a,
            )
        self.assertEqual(cm.exception.status_code, 403)
        self.assertEqual(cm.exception.code, "FORBIDDEN")


if __name__ == "__main__":
    unittest.main()
