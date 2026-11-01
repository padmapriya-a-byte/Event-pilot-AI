"""EventPilot AI - Automated Test Suite for Deliverables & Plan Exports API.

Tests:
  - Generation and downloading of all 4 supported export types:
      1. 'pdf_summary' (binary PDF-1.4 file)
      2. 'ics_calendar' (RFC 5545 iCalendar stream)
      3. 'csv_budget' (RFC 4180 CSV export)
      4. 'json_backup' (structured JSON event backup)
  - Ownership authorization and cross-event isolation.
  - Foreign key boundary verification (cross-event plan_id rejected).
  - Deletion of export metadata and storage artifacts.
"""

import json
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
from app.services.export_service import ExportService
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


class MockStorageBucket:
    """Mock Supabase Storage bucket simulating upload, download, and remove."""

    def __init__(self, bucket_name: str = "plan-exports"):
        self.bucket_name = bucket_name
        self.files: Dict[str, bytes] = {}
        self.simulate_upload_failure: bool = False
        self.simulate_download_failure: bool = False
        self.deleted_paths: List[str] = []

    def upload(self, path: str, file: Any, file_options: Optional[Dict[str, Any]] = None):
        if self.simulate_upload_failure:
            raise Exception("Simulated storage upload failure (500 Internal Server Error)")
        file_bytes = file if isinstance(file, bytes) else file.read()
        self.files[path] = file_bytes
        return {"Key": f"{self.bucket_name}/{path}"}

    def download(self, path: str) -> bytes:
        if self.simulate_download_failure:
            raise Exception("Simulated storage download failure (500 Internal Server Error)")
        if path not in self.files:
            raise Exception(f"File not found: {path} (404 Not Found)")
        return self.files[path]

    def remove(self, paths: List[str]):
        for p in paths:
            self.deleted_paths.append(p)
            self.files.pop(p, None)
        return [{"name": p} for p in paths]


class MockStorageDict(dict):
    """Dual-interface dictionary supporting database tables and Supabase Storage .from_()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buckets: Dict[str, MockStorageBucket] = {}

    def from_(self, bucket_name: str) -> MockStorageBucket:
        if bucket_name not in self.buckets:
            self.buckets[bucket_name] = MockStorageBucket(bucket_name)
        return self.buckets[bucket_name]


class MockQueryBuilder:
    def __init__(
        self,
        table_name: str,
        storage: Dict[str, List[Dict[str, Any]]],
        simulate_insert_failure: bool = False,
    ):
        self.table_name = table_name
        self.storage = storage
        self.simulate_insert_failure = simulate_insert_failure
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
        if self._action == "insert" and self.simulate_insert_failure:
            raise Exception("Simulated database failure during metadata insert: 23505 unique constraint violation")

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
        self.storage = MockStorageDict({
            "events": [],
            "event_preferences": [],
            "event_plans": [],
            "budget_items": [],
            "venues": [],
            "agenda_sessions": [],
            "tasks": [],
            "plan_exports": [],
        })
        self.simulate_insert_failure: bool = False

    def table(self, table_name: str) -> MockQueryBuilder:
        return MockQueryBuilder(
            table_name,
            self.storage,
            simulate_insert_failure=self.simulate_insert_failure,
        )


class MockAdminService:
    def __init__(self, client: Optional[MockSupabaseClient] = None):
        self._client = client or MockSupabaseClient()

    @property
    def client(self) -> MockSupabaseClient:
        return self._client


class ExportsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        self.mock_supabase = MockSupabaseClient()
        self.mock_admin_service = MockAdminService(self.mock_supabase)
        self.export_service = ExportService(self.mock_admin_service)

        self.app.config["EXPORT_SERVICE"] = self.export_service

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
            "title": "Global Tech Summit 2026",
            "event_type": "conference",
            "status": "planning",
            "start_date": "2026-11-15T09:00:00Z",
            "end_date": "2026-11-17T18:00:00Z",
            "timezone": "America/New_York",
            "currency": "USD",
            "target_budget": 50000.00,
            "expected_attendees": 500,
            "description": "Annual flagship technology summit",
            "is_archived": False,
        })

        # Event A2
        self.event_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["events"].append({
            "id": self.event_a2_id,
            "owner_id": self.user_a_id,
            "title": "Local Meetup",
            "is_archived": False,
        })

        # Active Plan for Event A1
        self.plan_a1_id = str(uuid.uuid4())
        self.mock_supabase.storage["event_plans"].append({
            "id": self.plan_a1_id,
            "event_id": self.event_a1_id,
            "title": "Summit Master Plan",
            "summary": "Master operations plan for the 3-day tech summit",
            "revision_number": 1,
            "is_active": True,
            "content": {"theme": "Innovation & Autonomy"},
        })

        # Plan belonging to Event A2
        self.plan_a2_id = str(uuid.uuid4())
        self.mock_supabase.storage["event_plans"].append({
            "id": self.plan_a2_id,
            "event_id": self.event_a2_id,
            "title": "Meetup Plan",
            "revision_number": 1,
            "is_active": True,
        })

        # Add budget items for Event A1 using actual schema columns from migration 00004
        self.mock_supabase.storage["budget_items"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "name": "Main Convention Hall",
            "category": "venue",
            "estimated_amount": 20000.00,
            "confirmed_amount": 19500.00,
            "actual_amount": 19500.00,
            "paid_amount": 10000.00,
            "payment_status": "partially_paid",
            "due_date": "2026-11-01",
            "notes": "50% deposit paid",
        })

        # Add agenda session for Event A1
        self.mock_supabase.storage["agenda_sessions"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "title": "Opening Keynote",
            "description": "Welcoming remarks and future outlook",
            "room_location": "Main Auditorium",
            "start_time": "2026-11-15T09:30:00Z",
            "end_time": "2026-11-15T10:30:00Z",
            "session_type": "keynote",
            "sort_order": 1,
        })

        # Add venue for Event A1
        self.mock_supabase.storage["venues"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "name": "Metro Convention Center",
            "is_selected": True,
            "capacity": 800,
        })

        # Add task for Event A1
        self.mock_supabase.storage["tasks"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "title": "Sign AV contract",
            "status": "todo",
            "priority": "high",
            "sort_order": 0,
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
    # 1. PDF Summary Export Tests
    # =========================================================================

    def test_export_pdf_summary_generate_and_download(self):
        """Generates a PDF summary deliverable and verifies valid PDF-1.4 file download."""
        # 1. Trigger export generation
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "pdf_summary"},
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()["data"]
        export_id = data["id"]
        self.assertEqual(data["export_type"], "pdf_summary")
        self.assertEqual(data["mime_type"], "application/pdf")
        self.assertGreater(data["file_size_bytes"], 0)
        self.assertIn("exports/", data["storage_path"])

        # 2. Download deliverable
        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.headers["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="', dl_res.headers["Content-Disposition"])

        # 3. Validate binary PDF structure
        pdf_bytes = dl_res.data
        self.assertTrue(pdf_bytes.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pdf_bytes.endswith(b"%%EOF\n"))
        self.assertIn(b"/Type /Catalog", pdf_bytes)

    # =========================================================================
    # 2. iCalendar Export Tests
    # =========================================================================

    def test_export_ics_calendar_generate_and_download(self):
        """Generates an RFC 5545 iCalendar stream with agenda sessions and verifies download."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "ics_calendar"},
        )
        self.assertEqual(res.status_code, 201)
        export_id = res.get_json()["data"]["id"]

        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.mimetype, "text/calendar")

        ics_text = dl_res.data.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("VERSION:2.0", ics_text)
        self.assertIn("BEGIN:VEVENT", ics_text)
        self.assertIn("SUMMARY:Opening Keynote", ics_text)
        self.assertIn("LOCATION:Main Auditorium", ics_text)
        self.assertIn("END:VCALENDAR", ics_text)

    # =========================================================================
    # 3. CSV Budget Export Tests
    # =========================================================================

    def test_export_csv_budget_generate_and_download(self):
        """Generates an RFC 4180 CSV budget deliverable with item and summary rows."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "csv_budget"},
        )
        self.assertEqual(res.status_code, 201)
        export_id = res.get_json()["data"]["id"]

        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.mimetype, "text/csv")

        csv_text = dl_res.data.decode("utf-8")
        self.assertIn("Main Convention Hall", csv_text)
        self.assertIn("50% deposit paid", csv_text)
        self.assertIn("20000.00", csv_text)
        self.assertIn("19500.00", csv_text)
        self.assertIn("Total Estimated", csv_text)
        self.assertIn("Remaining Budget", csv_text)

    def test_export_csv_budget_schema_column_mapping(self):
        """Verifies that budget items using schema columns (name, estimated_amount, etc.) map accurately into CSV."""
        # Add another item with explicit amounts
        self.mock_supabase.storage["budget_items"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "name": "Audio Visual Rigging",
            "category": "av_production",
            "estimated_amount": 5500.00,
            "confirmed_amount": 5000.00,
            "actual_amount": 4800.00,
            "paid_amount": 4800.00,
            "payment_status": "paid",
            "due_date": "2026-11-05",
            "notes": "Paid in full via wire",
        })

        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "csv_budget"},
        )
        self.assertEqual(res.status_code, 201)
        export_id = res.get_json()["data"]["id"]

        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        csv_text = dl_res.data.decode("utf-8")

        # Verify column headers align with schema
        self.assertIn("Item Name,Category,Estimated Amount (USD),Confirmed Amount (USD),Actual Amount (USD),Paid Amount (USD),Payment Status,Due Date,Notes", csv_text)
        # Verify row content
        self.assertIn("Audio Visual Rigging,av_production,5500.00,5000.00,4800.00,4800.00,paid,2026-11-05,Paid in full via wire", csv_text)
        # Verify totals: 20000 + 5500 = 25500.00
        self.assertIn("Total Estimated,25500.00", csv_text)
        # Total Confirmed: 19500 + 5000 = 24500.00
        self.assertIn("Total Confirmed,24500.00", csv_text)

    def test_export_csv_formula_injection_defense(self):
        """Verifies that cells starting with =, +, -, @ are sanitized with leading single quote."""
        self.mock_supabase.storage["budget_items"].append({
            "id": str(uuid.uuid4()),
            "event_id": self.event_a1_id,
            "name": "=SUM(A1:A10)",
            "category": "other",
            "estimated_amount": 100.00,
            "confirmed_amount": 100.00,
            "actual_amount": 100.00,
            "paid_amount": 0.00,
            "payment_status": "unpaid",
            "due_date": "2026-11-10",
            "notes": "@danger+calc",
        })

        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "csv_budget"},
        )
        self.assertEqual(res.status_code, 201)
        export_id = res.get_json()["data"]["id"]

        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        csv_text = dl_res.data.decode("utf-8")

        # Verify formula characters were prepended with single quote
        self.assertIn("'=SUM(A1:A10)", csv_text)
        self.assertIn("'@danger+calc", csv_text)
        self.assertNotIn("\n=SUM(A1:A10)", csv_text)

    # =========================================================================
    # 4. JSON Backup Export Tests
    # =========================================================================

    def test_export_json_backup_generate_and_download(self):
        """Generates a complete structured JSON dump of all event components."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "json_backup"},
        )
        self.assertEqual(res.status_code, 201)
        export_id = res.get_json()["data"]["id"]

        dl_res = self.client.get(
            f"/api/events/{self.event_a1_id}/exports/{export_id}/download",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(dl_res.status_code, 200)
        self.assertEqual(dl_res.headers["Content-Type"], "application/json")

        backup = json.loads(dl_res.data.decode("utf-8"))
        self.assertEqual(backup["version"], "1.0")
        self.assertEqual(backup["event"]["title"], "Global Tech Summit 2026")
        self.assertEqual(backup["active_plan"]["title"], "Summit Master Plan")
        self.assertEqual(len(backup["venues"]), 1)
        self.assertEqual(len(backup["agenda_sessions"]), 1)
        self.assertEqual(len(backup["tasks"]), 1)

    # =========================================================================
    # 5. Boundary & Authorization Tests
    # =========================================================================

    def test_export_unsupported_type_rejected(self):
        """Rejects export types not in the approved database enum."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "xml_spreadsheet"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_export_cross_event_plan_boundary_rejected(self):
        """Rejects export generation when referencing a plan belonging to another event."""
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={
                "export_type": "pdf_summary",
                "plan_id": self.plan_a2_id,  # Belongs to Event A2!
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "CROSS_EVENT_REFERENCE_FORBIDDEN")

    def test_export_ownership_and_cross_event_isolation(self):
        """User B cannot generate or access User A's exports; cross-event retrieval returns 404."""
        # 1. User B forbidden on User A's event
        res_b = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_b}"},
            json={"export_type": "pdf_summary"},
        )
        self.assertEqual(res_b.status_code, 403)

        # 2. Create export under Event A1
        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "json_backup"},
        )
        exp_id = res.get_json()["data"]["id"]

        # 3. Query under Event A2 -> 404
        cross_res = self.client.get(
            f"/api/events/{self.event_a2_id}/exports/{exp_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(cross_res.status_code, 404)

        # 4. Delete export under Event A1 -> 200
        del_res = self.client.delete(
            f"/api/events/{self.event_a1_id}/exports/{exp_id}",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
        )
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json()["data"]["deleted"])

    # =========================================================================
    # 7. Storage Reliability, Error Handling, and Orphan Cleanup Tests
    # =========================================================================

    def test_export_storage_upload_failure_fails_safely(self):
        """Storage upload failure fails safely with 502 STORAGE_ERROR and records no metadata."""
        bucket = self.mock_supabase.storage.from_("plan-exports")
        bucket.simulate_upload_failure = True

        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "pdf_summary"},
        )
        self.assertEqual(res.status_code, 502)
        err = res.get_json()["error"]
        self.assertEqual(err["code"], "STORAGE_ERROR")
        self.assertEqual(err["message"], "Failed to store export deliverable in storage service.")

        # Ensure no orphan metadata record was inserted
        exports_in_db = self.mock_supabase.storage.get("plan_exports", [])
        self.assertEqual(len(exports_in_db), 0)

    def test_export_metadata_insertion_failure_cleans_up_uploaded_file(self):
        """Compensating cleanup: uploaded file is deleted if metadata DB insertion fails."""
        bucket = self.mock_supabase.storage.from_("plan-exports")
        self.mock_supabase.simulate_insert_failure = True

        res = self.client.post(
            f"/api/events/{self.event_a1_id}/exports",
            headers={"Authorization": f"Bearer {self.token_user_a}"},
            json={"export_type": "csv_budget"},
        )
        # Should fail with database error
        self.assertIn(res.status_code, [409, 500])

        # Verify that compensating deletion ran and deleted the uploaded object
        self.assertEqual(len(bucket.deleted_paths), 1)
        self.assertEqual(len(bucket.files), 0, "Orphaned storage object was not cleaned up!")

    def test_export_service_configurable_bucket(self):
        """ExportService respects custom configured storage bucket."""
        custom_bucket_name = "custom-plan-deliverables"
        custom_service = ExportService(
            admin_service=self.mock_admin_service,
            bucket_name=custom_bucket_name,
        )
        self.assertEqual(custom_service.bucket_name, custom_bucket_name)

        # Generate an export using the custom service
        exp = custom_service.generate_export(
            event_id=self.event_a1_id,
            export_type="json_backup",
            user_id=self.user_a_id,
        )
        self.assertIsNotNone(exp)

        # Verify file was uploaded into the custom bucket
        custom_bucket = self.mock_supabase.storage.from_(custom_bucket_name)
        self.assertIn(exp["storage_path"], custom_bucket.files)

    def test_export_production_without_storage_client_fails_safely(self):
        """In production mode without storage client, service fails safely and does not use in-memory fallback."""
        class DummyClientWithoutStorage:
            def __init__(self, table_func):
                self.table = table_func

        dummy_client = DummyClientWithoutStorage(self.mock_supabase.table)
        strict_service = ExportService(
            admin_service=MockAdminService(dummy_client),
            use_in_memory_storage=False,
        )

        with self.assertRaises(APIError) as cm:
            strict_service.generate_export(
                event_id=self.event_a1_id,
                export_type="ics_calendar",
                user_id=self.user_a_id,
            )
        self.assertEqual(cm.exception.status_code, 503)
        self.assertEqual(cm.exception.code, "SERVICE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
