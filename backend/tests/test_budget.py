"""EventPilot AI - Automated Test Suite for Budget Service & Budget API.

Tests Budget Items CRUD, monetary precision, overflow handling, aggregation summaries,
distinct amounts (estimated, confirmed, actual, paid), remaining budget formulas,
item-to-event association, cross-event boundary security, and error handling.
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
from app.services.budget_service import BudgetService
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
    """In-memory Postgrest-like query builder simulating Supabase table/view operations."""

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
                inserted_list.append(dict(new_row))
            return type("APIResponse", (), {"data": inserted_list})()

        # Apply equality filters
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
    """Mock Supabase client providing .table() access to simulated tables and views."""

    def __init__(self):
        self.storage: Dict[str, List[Dict[str, Any]]] = {
            "events": [],
            "budget_items": [],
            "event_budget_summaries": [],
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


class BudgetTestCase(unittest.TestCase):
    """Test suite for Budget Service and Budget API endpoints."""

    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        # Initialize mock Supabase client and service
        self.mock_supabase = MockSupabaseClient()
        self.mock_admin_service = MockAdminService(self.mock_supabase)
        self.budget_service = BudgetService(self.mock_admin_service)

        # Wire budget service into app config
        self.app.config["BUDGET_SERVICE"] = self.budget_service

        # Event ownership resolver hook
        def mock_event_resolver(event_id: str):
            res = self.mock_supabase.table("events").select("*").eq("id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None

        self.app.config["EVENT_RESOLVER"] = mock_event_resolver

        # Set up test users
        self.user_a_id = "11111111-1111-1111-1111-111111111111"
        self.user_b_id = "22222222-2222-2222-2222-222222222222"

        self.token_user_a = self._generate_token(self.user_a_id, "user_a@eventpilot.ai")
        self.token_user_b = self._generate_token(self.user_b_id, "user_b@eventpilot.ai")

        # Create Event A1 (owned by User A, target_budget = 10000.00)
        self.event_a1_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a1_id,
            "owner_id": self.user_a_id,
            "title": "User A Tech Conference",
            "event_type": "conference",
            "status": "planning",
            "currency": "USD",
            "target_budget": 10000.00,
            "is_archived": False,
        })

        # Create Event A2 (owned by User A, target_budget = 5000.00)
        self.event_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a2_id,
            "owner_id": self.user_a_id,
            "title": "User A Hackathon",
            "event_type": "hackathon",
            "status": "draft",
            "currency": "USD",
            "target_budget": 5000.00,
            "is_archived": False,
        })

        # Create Event B1 (owned by User B)
        self.event_b1_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_b1_id,
            "owner_id": self.user_b_id,
            "title": "User B Secret Meeting",
            "event_type": "corporate",
            "status": "planning",
            "currency": "EUR",
            "target_budget": 20000.00,
            "is_archived": False,
        })

    def _generate_token(self, user_id: str, email: str = "user@eventpilot.ai") -> str:
        """Helper to create signed JWT for authentication."""
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
    # 1. Budget Item Creation Tests (POST /api/events/<event_id>/budget/items)
    # =========================================================================

    def test_create_budget_item_minimal(self):
        """User A can create a budget item with minimal required fields (defaults to 0.00 and unpaid)."""
        payload = {
            "category": "venue",
            "name": "Main Hall Deposit",
        }
        response = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()["data"]
        self.assertEqual(data["name"], "Main Hall Deposit")
        self.assertEqual(data["category"], "venue")
        self.assertEqual(data["event_id"], self.event_a1_id)
        self.assertEqual(data["estimated_amount"], 0.00)
        self.assertEqual(data["confirmed_amount"], 0.00)
        self.assertEqual(data["actual_amount"], 0.00)
        self.assertEqual(data["paid_amount"], 0.00)
        self.assertEqual(data["payment_status"], "unpaid")

    def test_create_budget_item_distinct_amounts(self):
        """Creates item with all 4 distinct amounts and ensures they remain distinct."""
        payload = {
            "category": "catering",
            "name": "Buffet Dinner",
            "estimated_amount": 2500.00,
            "confirmed_amount": 2400.00,
            "actual_amount": 2350.50,
            "paid_amount": 1000.00,
            "payment_status": "partially_paid",
            "due_date": "2026-11-15",
            "notes": "50% deposit paid upon contract signing",
        }
        response = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()["data"]
        self.assertEqual(data["estimated_amount"], 2500.00)
        self.assertEqual(data["confirmed_amount"], 2400.00)
        self.assertEqual(data["actual_amount"], 2350.50)
        self.assertEqual(data["paid_amount"], 1000.00)
        self.assertEqual(data["payment_status"], "partially_paid")
        self.assertEqual(data["due_date"], "2026-11-15")
        self.assertEqual(data["notes"], "50% deposit paid upon contract signing")

    def test_create_budget_item_ignores_client_supplied_event_id(self):
        """Client supplying spoofed event_id or id in request body is ignored; bound to route event_id."""
        payload = {
            "category": "decor",
            "name": "Flowers",
            "event_id": self.event_b1_id,  # Spoofed event
            "id": str(uuid.uuid4()),        # Spoofed ID
        }
        response = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(response.status_code, 201)
        data = response.get_json()["data"]
        self.assertEqual(data["event_id"], self.event_a1_id)
        self.assertNotEqual(data["event_id"], self.event_b1_id)

    def test_create_budget_item_validation_failures(self):
        """Rejects missing/invalid category, empty name, negative amounts, overflow, and invalid statuses."""
        # 1. Missing category
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Test Item"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "VALIDATION_ERROR")

        # 2. Invalid category (not in allowed 11 categories)
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Test Item", "category": "invalid_category"},
        )
        self.assertEqual(res.status_code, 400)

        # 3. Empty name
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "   ", "category": "venue"},
        )
        self.assertEqual(res.status_code, 400)

        # 4. Negative amounts
        for field in ("estimated_amount", "confirmed_amount", "actual_amount", "paid_amount"):
            res = self.client.post(
                f"/api/events/{self.event_a1_id}/budget/items",
                headers={"Authorization": f"Bearer {self.token_user_a}"},
                json={"name": "Item", "category": "venue", field: -10.00},
            )
            self.assertEqual(res.status_code, 400)
            self.assertIn("cannot be negative", res.get_json()["error"]["message"])

        # 5. Numeric overflow (> 9,999,999,999.99)
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Item", "category": "venue", "estimated_amount": 10_000_000_000.00},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceeds maximum allowed", res.get_json()["error"]["message"])

        # 6. Invalid payment status
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Item", "category": "venue", "payment_status": "unknown_status"},
        )
        self.assertEqual(res.status_code, 400)

        # 7. Invalid due_date format
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Item", "category": "venue", "due_date": "not-a-date"},
        )
        self.assertEqual(res.status_code, 400)

    def test_create_budget_item_other_user_forbidden(self):
        """User B cannot create an item for User A's event."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"name": "Spy Equipment", "category": "other"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.get_json()["error"]["code"], "FORBIDDEN")

    # =========================================================================
    # 2. Budget Item Listing Tests (GET /api/events/<event_id>/budget/items)
    # =========================================================================

    def test_list_budget_items_ownership_isolation(self):
        """Listing budget items strictly returns items for the queried event and enforces event ownership."""
        # Create 2 items for Event A1
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "venue", "name": "Event A1 Venue", "estimated_amount": 5000.00},
        )
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "catering", "name": "Event A1 Catering", "estimated_amount": 2000.00},
        )

        # Create 1 item for Event B1
        self.client.post(
            f"/api/events/{self.event_b1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"category": "entertainment", "name": "Event B1 Band", "estimated_amount": 3000.00},
        )

        # User A lists Event A1
        res = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["data"]
        self.assertEqual(len(items), 2)
        for it in items:
            self.assertEqual(it["event_id"], self.event_a1_id)

        # User B cannot list Event A1
        forbidden_res = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(forbidden_res.status_code, 403)

    def test_list_budget_items_filtering(self):
        """Supports filtering by category and payment_status."""
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "venue", "name": "Stage Rental", "payment_status": "paid"},
        )
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "catering", "name": "Coffee Bar", "payment_status": "unpaid"},
        )

        # Filter by category=catering
        res_cat = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items?category=catering",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        data_cat = res_cat.get_json()["data"]
        self.assertEqual(len(data_cat), 1)
        self.assertEqual(data_cat[0]["name"], "Coffee Bar")

        # Filter by payment_status=paid
        res_status = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items?payment_status=paid",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        data_status = res_status.get_json()["data"]
        self.assertEqual(len(data_status), 1)
        self.assertEqual(data_status[0]["name"], "Stage Rental")

    # =========================================================================
    # 3. Budget Item Get, Update & Delete Tests
    # =========================================================================

    def test_get_budget_item_success_and_cross_event_rejection(self):
        """Owner can retrieve item, but cross-event reference is rejected with 404."""
        create_res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "marketing", "name": "Social Ads", "estimated_amount": 500.00},
        )
        item_id = create_res.get_json()["data"]["id"]

        # Valid fetch under Event A1
        get_res = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.get_json()["data"]["id"], item_id)

        # Invalid cross-event fetch: Item belongs to Event A1, but requested under Event A2
        cross_res = self.client.get(
            f"/api/events/{self.event_a2_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_res.status_code, 404)
        self.assertEqual(cross_res.get_json()["error"]["code"], "NOT_FOUND")

    def test_update_budget_item_success(self):
        """Owner can update monetary amounts, payment status, and notes."""
        create_res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "staffing", "name": "Security Guards", "estimated_amount": 1000.00},
        )
        item_id = create_res.get_json()["data"]["id"]

        update_payload = {
            "confirmed_amount": 950.00,
            "actual_amount": 950.00,
            "paid_amount": 950.00,
            "payment_status": "paid",
            "notes": "Paid in full via bank transfer",
        }
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=update_payload,
        )
        self.assertEqual(patch_res.status_code, 200)
        data = patch_res.get_json()["data"]
        self.assertEqual(data["confirmed_amount"], 950.00)
        self.assertEqual(data["actual_amount"], 950.00)
        self.assertEqual(data["paid_amount"], 950.00)
        self.assertEqual(data["payment_status"], "paid")
        self.assertEqual(data["notes"], "Paid in full via bank transfer")

    def test_update_budget_item_invalid_cross_event_rejection(self):
        """Cannot update an item via a different event route."""
        create_res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "transportation", "name": "Shuttle Bus"},
        )
        item_id = create_res.get_json()["data"]["id"]

        patch_res = self.client.patch(
            f"/api/events/{self.event_a2_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"actual_amount": 300.00},
        )
        self.assertEqual(patch_res.status_code, 404)

    def test_delete_budget_item_success_and_cross_event_rejection(self):
        """Owner can delete an item, but cross-event deletion is rejected."""
        create_res = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"category": "permits", "name": "Noise Permit", "estimated_amount": 150.00},
        )
        item_id = create_res.get_json()["data"]["id"]

        # Attempt deletion under wrong event -> 404
        cross_del = self.client.delete(
            f"/api/events/{self.event_a2_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_del.status_code, 404)

        # Successful deletion under correct event -> 200
        del_res = self.client.delete(
            f"/api/events/{self.event_a1_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

        # Fetching deleted item returns 404
        get_res = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/items/{item_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(get_res.status_code, 404)

    # =========================================================================
    # 4. Budget Aggregation & Summary Tests (GET /summary and /budget)
    # =========================================================================

    def test_budget_summary_aggregation_formulas(self):
        """Verifies distinct totals and remaining budget formula (target_budget - total_actual)."""
        # Event A1 target_budget is 10000.00 USD
        # Item 1: Venue
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "category": "venue",
                "name": "Convention Center",
                "estimated_amount": 5000.00,
                "confirmed_amount": 4800.00,
                "actual_amount": 4800.00,
                "paid_amount": 4800.00,
                "payment_status": "paid",
            },
        )
        # Item 2: Catering
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "category": "catering",
                "name": "Lunch Buffet",
                "estimated_amount": 2500.00,
                "confirmed_amount": 2400.00,
                "actual_amount": 2200.00,
                "paid_amount": 1000.00,
                "payment_status": "partially_paid",
            },
        )
        # Item 3: AV Production
        self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "category": "av_production",
                "name": "Projector & Sound",
                "estimated_amount": 1000.00,
                "confirmed_amount": 900.00,
                "actual_amount": 800.00,
                "paid_amount": 0.00,
                "payment_status": "unpaid",
            },
        )

        response = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/summary",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]

        # Expected totals:
        # total_estimated = 5000 + 2500 + 1000 = 8500.00
        # total_confirmed = 4800 + 2400 + 900  = 8100.00
        # total_actual    = 4800 + 2200 + 800  = 7800.00
        # total_paid      = 4800 + 1000 + 0    = 5800.00
        # remaining_budget = 10000.00 - 7800.00 = 2200.00
        self.assertEqual(data["event_id"], self.event_a1_id)
        self.assertEqual(data["target_budget"], 10000.00)
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["total_estimated"], 8500.00)
        self.assertEqual(data["total_confirmed"], 8100.00)
        self.assertEqual(data["total_actual"], 7800.00)
        self.assertEqual(data["total_paid"], 5800.00)
        self.assertEqual(data["remaining_budget"], 2200.00)

        # Check category breakdowns
        breakdowns = data["category_breakdowns"]
        self.assertIn("venue", breakdowns)
        self.assertEqual(breakdowns["venue"]["actual"], 4800.00)
        self.assertEqual(breakdowns["venue"]["paid"], 4800.00)

        self.assertIn("catering", breakdowns)
        self.assertEqual(breakdowns["catering"]["estimated"], 2500.00)
        self.assertEqual(breakdowns["catering"]["actual"], 2200.00)
        self.assertEqual(breakdowns["catering"]["paid"], 1000.00)

        self.assertIn("av_production", breakdowns)
        self.assertEqual(breakdowns["av_production"]["actual"], 800.00)

        # Convenience route /api/events/<event_id>/budget returns identical summary
        alias_res = self.client.get(
            f"/api/events/{self.event_a1_id}/budget",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(alias_res.status_code, 200)
        self.assertEqual(alias_res.get_json()["data"]["remaining_budget"], 2200.00)

    def test_budget_summary_empty_event(self):
        """Event with no budget items returns 0.00 totals and remaining_budget == target_budget."""
        response = self.client.get(
            f"/api/events/{self.event_a2_id}/budget/summary",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["total_estimated"], 0.00)
        self.assertEqual(data["total_confirmed"], 0.00)
        self.assertEqual(data["total_actual"], 0.00)
        self.assertEqual(data["total_paid"], 0.00)
        self.assertEqual(data["remaining_budget"], 5000.00)  # Event A2 target_budget is 5000.00
        self.assertEqual(data["category_breakdowns"], {})

    def test_budget_summary_other_user_forbidden(self):
        """User B cannot view User A's event budget summary."""
        response = self.client.get(
            f"/api/events/{self.event_a1_id}/budget/summary",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "FORBIDDEN")

    # =========================================================================
    # 5. Database Service Failure Handling Tests
    # =========================================================================

    def test_database_service_unconfigured_fails_closed(self):
        """Unconfigured Supabase service fails closed with 503 SERVICE_UNAVAILABLE."""
        unconfigured_service = MockAdminService(is_configured=False)
        svc = BudgetService(unconfigured_service)
        self.app.config["BUDGET_SERVICE"] = svc

        response = self.client.post(
            f"/api/events/{self.event_a1_id}/budget/items",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"name": "Failing Item", "category": "venue"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"]["code"], "SERVICE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
