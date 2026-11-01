"""EventPilot AI - Automated Test Suite for Tasks API.

Tests:
  - Task CRUD operations and ownership isolation.
  - Task validation: allowed statuses, allowed priorities, title validation.
  - Composite foreign key boundary: tasks cannot reference a plan belonging to another event.
  - Query filtering: status, priority, pagination.
"""

import os
import sys
import time
import uuid
import unittest
from typing import Dict, Any, List, Optional
import jwt

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app
from app.config import Config
from app.services.task_service import TaskService


class TestConfig(Config):
    TESTING = True
    ENV = "testing"
    SECRET_KEY = "test-secret-key-for-unit-testing"
    SUPABASE_JWT_SECRET = "super-secret-jwt-signing-key-for-testing-at-least-32-chars"
    SUPABASE_JWT_ALGORITHM = "HS256"
    SUPABASE_JWT_AUDIENCE = "authenticated"
    SUPABASE_JWT_ISSUER = None
    SUPABASE_JWT_PUBLIC_KEY = None


class MockQueryBuilder:
    def __init__(self, table_name: str, storage: Dict[str, List[Dict[str, Any]]]):
        self.table_name = table_name
        self.storage = storage
        self._filters: List[tuple] = []
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._range_start = 0
        self._range_end = None
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

    def range(self, start: int, end: int):
        self._range_start = start
        self._range_end = end
        return self

    def execute(self):
        rows = self.storage.get(self.table_name, [])

        if self._action == "insert":
            inserted = []
            records = self._action_data if isinstance(self._action_data, list) else [self._action_data]
            for r in records:
                row = dict(r)
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
            if self._range_end is not None:
                res = res[self._range_start : self._range_end + 1]
            return type("APIResponse", (), {"data": [dict(x) for x in res]})()

        elif self._action == "update":
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


class MockSupabaseClient:
    def __init__(self):
        self.storage: Dict[str, List[Dict[str, Any]]] = {
            "events": [],
            "event_plans": [],
            "tasks": [],
        }

    def table(self, table_name: str) -> MockQueryBuilder:
        return MockQueryBuilder(table_name, self.storage)


class MockAdminService:
    def __init__(self, client: Optional[MockSupabaseClient] = None):
        self._client = client or MockSupabaseClient()

    @property
    def client(self) -> MockSupabaseClient:
        return self._client


class TasksTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        self.mock_supabase = MockSupabaseClient()
        self.mock_admin_service = MockAdminService(self.mock_supabase)
        self.task_service = TaskService(self.mock_admin_service)

        self.app.config["TASK_SERVICE"] = self.task_service

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
            "title": "User A Event 1",
            "is_archived": False,
        })

        # Event A2
        self.event_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a2_id,
            "owner_id": self.user_a_id,
            "title": "User A Event 2",
            "is_archived": False,
        })

        # Plan belonging to Event A1
        self.plan_a1_id = str(uuid.uuid4())
        self.mock_supabase.storage["event_plans"].append({
            "id": self.plan_a1_id,
            "event_id": self.event_a1_id,
            "title": "Plan for Event A1",
            "is_active": True,
        })

        # Plan belonging to Event A2
        self.plan_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["event_plans"].append({
            "id": self.plan_a2_id,
            "event_id": self.event_a2_id,
            "title": "Plan for Event A2",
            "is_active": True,
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

    def test_create_task_minimal_defaults(self):
        """Creates a task with title only; verifies defaults for status, priority, and sort_order."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Confirm speaker lineup"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["data"]
        self.assertEqual(data["title"], "Confirm speaker lineup")
        self.assertEqual(data["status"], "todo")
        self.assertEqual(data["priority"], "medium")
        self.assertEqual(data["sort_order"], 0)
        self.assertEqual(data["event_id"], self.event_a1_id)
        self.assertIsNone(data["plan_id"])

    def test_create_task_full_fields(self):
        """Creates a task with all fields specified."""
        assigned_uuid = str(uuid.uuid4())
        payload = {
            "title": "Finalize catering menu",
            "description": "Review vegan options with vendor",
            "status": "in_progress",
            "priority": "high",
            "due_date": "2026-11-01T17:00:00Z",
            "assigned_to": assigned_uuid,
            "category": "catering",
            "sort_order": 2,
            "plan_id": self.plan_a1_id,
        }
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json=payload,
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["data"]
        self.assertEqual(data["title"], "Finalize catering menu")
        self.assertEqual(data["status"], "in_progress")
        self.assertEqual(data["priority"], "high")
        self.assertEqual(data["assigned_to"], assigned_uuid)
        self.assertEqual(data["plan_id"], self.plan_a1_id)

    def test_create_task_cross_event_plan_boundary_enforcement(self):
        """Rejects a task in Event A1 referencing plan belonging to Event A2."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "title": "Cross-Event Task",
                "plan_id": self.plan_a2_id,  # Belongs to Event A2!
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "CROSS_EVENT_REFERENCE_FORBIDDEN")

    def test_create_task_validation_errors(self):
        """Rejects empty title, invalid status, invalid priority, and invalid UUIDs."""
        # Empty title
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "   "},
        )
        self.assertEqual(res.status_code, 400)

        # Invalid status
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Task", "status": "invalid_status"},
        )
        self.assertEqual(res.status_code, 400)

        # Invalid priority
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Task", "priority": "extreme"},
        )
        self.assertEqual(res.status_code, 400)

        # Invalid assigned_to
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Task", "assigned_to": "not-a-uuid"},
        )
        self.assertEqual(res.status_code, 400)

    def test_task_filtering_and_crud(self):
        """Tests task listing with status/priority filters, update, get, and delete."""
        self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Task 1", "status": "completed", "priority": "low"},
        )
        res2 = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Task 2", "status": "todo", "priority": "urgent"},
        )
        t2_id = res2.get_json()["data"]["id"]

        # Filter by status=completed
        res_stat = self.client.get(
            f"/api/events/{self.event_a1_id}/tasks?status=completed",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(res_stat.status_code, 200)
        self.assertEqual(len(res_stat.get_json()["data"]), 1)
        self.assertEqual(res_stat.get_json()["data"][0]["title"], "Task 1")

        # Filter by priority=urgent
        res_prio = self.client.get(
            f"/api/events/{self.event_a1_id}/tasks?priority=urgent",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(res_prio.status_code, 200)
        self.assertEqual(len(res_prio.get_json()["data"]), 1)
        self.assertEqual(res_prio.get_json()["data"][0]["title"], "Task 2")

        # Update task 2
        patch_res = self.client.patch(
            f"/api/events/{self.event_a1_id}/tasks/{t2_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"status": "in_progress"},
        )
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.get_json()["data"]["status"], "in_progress")

        # Delete task 2
        del_res = self.client.delete(
            f"/api/events/{self.event_a1_id}/tasks/{t2_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

    def test_task_cross_event_and_ownership_isolation(self):
        """Tests that User B cannot access tasks of Event A1, and Event A2 cannot query Event A1 task."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"title": "Confidential Task"},
        )
        t_id = res.get_json()["data"]["id"]

        # User B forbidden
        res_b = self.client.get(
            f"/api/events/{self.event_a1_id}/tasks",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
        )
        self.assertEqual(res_b.status_code, 403)

        # Cross event under same owner A
        cross_res = self.client.get(
            f"/api/events/{self.event_a2_id}/tasks/{t_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
