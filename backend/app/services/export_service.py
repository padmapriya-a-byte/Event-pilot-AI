"""EventPilot AI - Plan Export Service Layer.

Implements generation, storage, and retrieval of event plan deliverables:
  - 'pdf_summary': Pure-Python PDF-1.4 binary summary of the event plan.
  - 'ics_calendar': RFC 5545 iCalendar schedule with agenda sessions.
  - 'csv_budget': RFC 4180 CSV export of event budget items and summaries.
  - 'json_backup': Full structured JSON dump of all event components.

Security & Architecture:
  - Restricts export types to the approved schema enum.
  - Validates composite foreign key boundaries (plan_id must belong to event_id).
  - Stores files in private storage paths (exports/{event_id}/{export_id}.{ext}).
  - Service role creates and manages export metadata in public.plan_exports.
  - Sanitizes all database and storage errors.
"""

import csv
from datetime import datetime, timezone
import io
import json
from typing import Dict, Any, List, Optional, Tuple
import uuid

from ..services.supabase_service import SupabaseAdminService
from ..config import Config
from ..utils.errors import APIError

ALLOWED_EXPORT_TYPES = {
    "pdf_summary",
    "ics_calendar",
    "csv_budget",
    "json_backup",
}

EXPORT_MIME_TYPES = {
    "pdf_summary": "application/pdf",
    "ics_calendar": "text/calendar",
    "csv_budget": "text/csv",
    "json_backup": "application/json",
}

EXPORT_EXTENSIONS = {
    "pdf_summary": "pdf",
    "ics_calendar": "ics",
    "csv_budget": "csv",
    "json_backup": "json",
}


def escape_ics_text(text: Optional[str]) -> str:
    """Escapes characters in text fields according to RFC 5545 section 3.3.11."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def sanitize_csv_cell(val: Any) -> str:
    """Sanitizes cell content to prevent CSV formula injection (CWE-1236).

    If the string begins with =, +, -, @, or tab/CR, prepends a single quote (').
    """
    if val is None:
        return ""
    text = str(val)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def format_ics_datetime(dt_str: Optional[str]) -> str:
    """Formats an ISO datetime string into RFC 5545 UTC representation (YYYYMMDDTHHMMSSZ)."""
    if not dt_str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        utc_dt = dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_pure_pdf(title: str, lines: List[str]) -> bytes:
    """Constructs a valid PDF-1.4 binary file with exact xref table and object offsets."""
    stream_lines = [
        "BT",
        "/F1 16 Tf",
        "50 740 Td",
        f"({title[:60]}) Tj",
        "/F1 10 Tf",
    ]
    y = 705
    for line in lines[:38]:
        escaped_line = (
            line.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        stream_lines.append(f"1 0 0 1 50 {y} Tm ({escaped_line[:85]}) Tj")
        y -= 16
    stream_lines.append("ET")
    stream_body = "\n".join(stream_lines)
    stream_bytes = stream_body.encode("latin1", errors="replace")

    objs: List[bytes] = []
    # 1 0 obj: Catalog
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    # 2 0 obj: Pages
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    # 3 0 obj: Page
    objs.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    # 4 0 obj: Font
    objs.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    # 5 0 obj: Contents Stream
    objs.append(
        f"5 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin1")
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )

    header = b"%PDF-1.4\n"
    body = b""
    offsets = [0]
    curr = len(header)
    for obj in objs:
        offsets.append(curr)
        body += obj
        curr += len(obj)

    xref_offset = len(header) + len(body)
    xref_str = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    for o in offsets[1:]:
        xref_str += f"{o:010d} 00000 n \n"
    trailer_str = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"

    return header + body + xref_str.encode("latin1") + trailer_str.encode("latin1")


class ExportService:
    """Service layer managing deliverables generation, storage, and metadata."""

    def __init__(
        self,
        admin_service: Optional[SupabaseAdminService] = None,
        bucket_name: Optional[str] = None,
        use_in_memory_storage: Optional[bool] = None,
    ):
        self._admin_service = admin_service or SupabaseAdminService()
        self.bucket_name = bucket_name or getattr(Config, "STORAGE_EXPORTS_BUCKET", "plan-exports")
        self._in_memory_storage: Dict[str, bytes] = {}

        if use_in_memory_storage is not None:
            self.use_in_memory_storage = use_in_memory_storage
        else:
            # Strictly disabled in production; permitted only when testing
            env = getattr(Config, "ENV", "development")
            is_testing = getattr(Config, "TESTING", False) or env == "testing"
            self.use_in_memory_storage = is_testing

    @property
    def client(self) -> Any:
        """Returns administrative Supabase client."""
        return self._admin_service.client

    @property
    def _storage_client(self) -> Any:
        """Returns the Supabase Storage client if available and supported."""
        if hasattr(self.client, "storage") and hasattr(self.client.storage, "from_"):
            return self.client.storage
        return None

    # =========================================================================
    # Generators for each deliverable format
    # =========================================================================

    def generate_pdf_summary(
        self,
        event: Dict[str, Any],
        plan: Optional[Dict[str, Any]],
        budget_summary: Dict[str, Any],
        agenda_sessions: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
    ) -> bytes:
        """Generates a PDF-1.4 summary document for the event and plan."""
        title = event.get("title", "Event Summary")
        selected_venue = next((v for v in venues if v.get("is_selected")), None)
        venue_str = f"Venue: {selected_venue.get('name', 'None')}" if selected_venue else "Venue: TBD"

        lines = [
            f"Event Type: {event.get('event_type', 'N/A').title()} | Status: {event.get('status', 'draft').title()}",
            f"Dates: {event.get('start_date', 'TBD')} to {event.get('end_date', 'TBD')} ({event.get('timezone', 'UTC')})",
            f"Expected Attendees: {event.get('expected_attendees', 'N/A')} | {venue_str}",
            "",
            "--- BUDGET OVERVIEW ---",
            f"Target Budget: {event.get('currency', 'USD')} {budget_summary.get('target_budget', 0.0):,.2f}",
            f"Total Estimated: {event.get('currency', 'USD')} {budget_summary.get('total_estimated', 0.0):,.2f}",
            f"Total Confirmed: {event.get('currency', 'USD')} {budget_summary.get('total_confirmed', 0.0):,.2f}",
            f"Total Actual: {event.get('currency', 'USD')} {budget_summary.get('total_actual', 0.0):,.2f}",
            f"Remaining Budget: {event.get('currency', 'USD')} {budget_summary.get('remaining_budget', 0.0):,.2f}",
            "",
            "--- ACTIVE PLAN OVERVIEW ---",
        ]

        if plan:
            lines.append(f"Plan: {plan.get('title', 'Master Plan')} (Rev #{plan.get('revision_number', 1)})")
            lines.append(f"Summary: {plan.get('summary', 'No summary provided.')[:80]}")
            content = plan.get("content") or {}
            if isinstance(content, dict):
                theme = content.get("theme")
                if theme:
                    lines.append(f"Theme: {theme}")
        else:
            lines.append("No active plan generated yet.")

        lines.extend(["", "--- AGENDA SCHEDULE ---"])
        if agenda_sessions:
            for s in agenda_sessions[:10]:
                start = s.get("start_time", "")[:16].replace("T", " ")
                lines.append(f"[{start}] {s.get('title', 'Session')} ({s.get('session_type', 'other')})")
        else:
            lines.append("No agenda sessions scheduled.")

        return build_pure_pdf(f"EventPilot AI: {title}", lines)

    def generate_ics_calendar(
        self,
        event: Dict[str, Any],
        agenda_sessions: List[Dict[str, Any]],
    ) -> bytes:
        """Generates an RFC 5545 iCalendar stream with event agenda sessions."""
        event_title = escape_ics_text(event.get("title", "Event Schedule"))
        cal_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//EventPilot AI//Event Schedule 1.0//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{event_title}",
            f"X-WR-TIMEZONE:{event.get('timezone', 'UTC')}",
        ]

        now_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        if not agenda_sessions:
            # Fallback single whole-event entry if no sessions
            cal_lines.extend([
                "BEGIN:VEVENT",
                f"UID:event-{event.get('id')}@eventpilot.ai",
                f"DTSTAMP:{now_utc}",
                f"DTSTART:{format_ics_datetime(event.get('start_date'))}",
                f"DTEND:{format_ics_datetime(event.get('end_date') or event.get('start_date'))}",
                f"SUMMARY:{event_title}",
                f"DESCRIPTION:{escape_ics_text(event.get('description'))}",
                "END:VEVENT",
            ])
        else:
            for session in agenda_sessions:
                s_id = session.get("id") or str(uuid.uuid4())
                s_title = escape_ics_text(session.get("title", "Session"))
                s_desc = escape_ics_text(session.get("description"))
                s_room = escape_ics_text(session.get("room_location"))
                dt_start = format_ics_datetime(session.get("start_time"))
                dt_end = format_ics_datetime(session.get("end_time"))

                event_block = [
                    "BEGIN:VEVENT",
                    f"UID:session-{s_id}@eventpilot.ai",
                    f"DTSTAMP:{now_utc}",
                    f"DTSTART:{dt_start}",
                    f"DTEND:{dt_end}",
                    f"SUMMARY:{s_title}",
                ]
                if s_desc:
                    event_block.append(f"DESCRIPTION:{s_desc}")
                if s_room:
                    event_block.append(f"LOCATION:{s_room}")
                event_block.append("END:VEVENT")
                cal_lines.extend(event_block)

        cal_lines.append("END:VCALENDAR\r\n")
        return "\r\n".join(cal_lines).encode("utf-8")

    def generate_csv_budget(
        self,
        event: Dict[str, Any],
        budget_items: List[Dict[str, Any]],
        budget_summary: Dict[str, Any],
    ) -> bytes:
        """Generates an RFC 4180 CSV export of event budget items with summary calculations."""
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\r\n")

        # Header metadata
        currency = event.get("currency", "USD")
        writer.writerow(["Event Title", sanitize_csv_cell(event.get("title", ""))])
        writer.writerow(["Currency", sanitize_csv_cell(currency)])
        writer.writerow(["Target Budget", f"{budget_summary.get('target_budget', 0.0):.2f}"])
        writer.writerow([])

        # Table header - aligns with public.budget_items schema
        writer.writerow([
            "Item Name",
            "Category",
            f"Estimated Amount ({currency})",
            f"Confirmed Amount ({currency})",
            f"Actual Amount ({currency})",
            f"Paid Amount ({currency})",
            "Payment Status",
            "Due Date",
            "Notes",
        ])

        # Item rows
        for item in budget_items:
            # Schema columns: name, category, estimated_amount, confirmed_amount, actual_amount, paid_amount, payment_status, due_date, notes
            name_val = item.get("name") if item.get("name") is not None else item.get("item_name", "")
            est_val = item.get("estimated_amount") if item.get("estimated_amount") is not None else item.get("estimated_cost", 0.0)
            conf_val = item.get("confirmed_amount") if item.get("confirmed_amount") is not None else item.get("confirmed_cost")
            act_val = item.get("actual_amount") if item.get("actual_amount") is not None else item.get("actual_cost")
            paid_val = item.get("paid_amount", 0.0)
            payment_status_val = item.get("payment_status", "unpaid")
            due_date_val = item.get("due_date", "")
            notes_val = item.get("notes", "")

            writer.writerow([
                sanitize_csv_cell(name_val),
                sanitize_csv_cell(item.get("category", "")),
                f"{float(est_val or 0.0):.2f}",
                f"{float(conf_val):.2f}" if conf_val is not None and conf_val != "" else "",
                f"{float(act_val):.2f}" if act_val is not None and act_val != "" else "",
                f"{float(paid_val or 0.0):.2f}",
                sanitize_csv_cell(payment_status_val),
                sanitize_csv_cell(due_date_val),
                sanitize_csv_cell(notes_val),
            ])

        # Summary footer
        writer.writerow([])
        writer.writerow(["--- BUDGET SUMMARY ---"])
        writer.writerow(["Total Estimated", f"{budget_summary.get('total_estimated', 0.0):.2f}"])
        writer.writerow(["Total Confirmed", f"{budget_summary.get('total_confirmed', 0.0):.2f}"])
        writer.writerow(["Total Actual", f"{budget_summary.get('total_actual', 0.0):.2f}"])
        writer.writerow(["Total Paid", f"{budget_summary.get('total_paid', 0.0):.2f}"])
        writer.writerow(["Remaining Budget", f"{budget_summary.get('remaining_budget', 0.0):.2f}"])

        return buf.getvalue().encode("utf-8")

    def generate_json_backup(
        self,
        event: Dict[str, Any],
        preferences: Optional[Dict[str, Any]],
        active_plan: Optional[Dict[str, Any]],
        budget_summary: Dict[str, Any],
        budget_items: List[Dict[str, Any]],
        venues: List[Dict[str, Any]],
        agenda_sessions: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
    ) -> bytes:
        """Generates a complete, structured JSON backup of all event data."""
        backup_data = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "preferences": preferences or {},
            "active_plan": active_plan,
            "budget": {
                "summary": budget_summary,
                "items": budget_items,
            },
            "venues": venues,
            "agenda_sessions": agenda_sessions,
            "tasks": tasks,
        }
        return json.dumps(backup_data, indent=2, default=str).encode("utf-8")

    # =========================================================================
    # Storage & Persistence Operations
    # =========================================================================

    def _save_to_storage(self, storage_path: str, file_bytes: bytes, mime_type: str) -> None:
        """Saves file to Supabase Storage or test-only in-memory storage.

        In production, requires persistent Supabase Storage and fails safely with a sanitized
        APIError if upload fails. Never silently treats in-memory fallback as persistent storage.
        """
        storage = self._storage_client
        if storage is not None:
            try:
                bucket = storage.from_(self.bucket_name)
                bucket.upload(
                    path=storage_path,
                    file=file_bytes,
                    file_options={"content-type": mime_type, "upsert": "true"},
                )
                return
            except Exception:
                raise APIError(
                    message="Failed to store export deliverable in storage service.",
                    status_code=502,
                    code="STORAGE_ERROR",
                )

        if self.use_in_memory_storage:
            self._in_memory_storage[storage_path] = file_bytes
            return

        raise APIError(
            message="Storage service is not configured on the server.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )

    def _download_from_storage(self, storage_path: str) -> bytes:
        """Retrieves file from Supabase Storage or test-only in-memory storage."""
        storage = self._storage_client
        if storage is not None:
            try:
                bucket = storage.from_(self.bucket_name)
                res = bucket.download(storage_path)
                if res:
                    return res if isinstance(res, bytes) else bytes(res)
            except Exception as e:
                err_str = str(e).lower()
                if "not found" in err_str or "404" in err_str or "nosuchkey" in err_str:
                    raise APIError(
                        message=f"Export file not found at storage path '{storage_path}'.",
                        status_code=404,
                        code="NOT_FOUND",
                    )
                raise APIError(
                    message="Failed to retrieve export file from storage service.",
                    status_code=502,
                    code="STORAGE_ERROR",
                )
            raise APIError(
                message=f"Export file not found at storage path '{storage_path}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        if self.use_in_memory_storage:
            if storage_path in self._in_memory_storage:
                return self._in_memory_storage[storage_path]
            raise APIError(
                message=f"Export file not found at storage path '{storage_path}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        raise APIError(
            message="Storage service is not configured on the server.",
            status_code=503,
            code="SERVICE_UNAVAILABLE",
        )

    def _delete_from_storage(self, storage_path: str) -> None:
        """Removes file from Supabase Storage and test in-memory storage."""
        storage = self._storage_client
        if storage is not None:
            try:
                bucket = storage.from_(self.bucket_name)
                bucket.remove([storage_path])
            except Exception:
                pass

        if self.use_in_memory_storage:
            self._in_memory_storage.pop(storage_path, None)

    # =========================================================================
    # Main Export Workflows
    # =========================================================================

    def generate_export(
        self,
        event_id: str,
        export_type: str,
        user_id: str,
        plan_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generates the requested export deliverable and records metadata via service role."""
        if export_type not in ALLOWED_EXPORT_TYPES:
            allowed_str = ", ".join(sorted(ALLOWED_EXPORT_TYPES))
            raise APIError(
                message=f"Field 'export_type' must be one of: {allowed_str}.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        # 1. Fetch Event
        event_res = self.client.table("events").select("*").eq("id", event_id).execute()
        if not event_res.data or len(event_res.data) == 0:
            raise APIError(f"Event with id '{event_id}' not found.", status_code=404, code="NOT_FOUND")
        event = event_res.data[0]

        # 2. Resolve Plan and verify boundary
        target_plan: Optional[Dict[str, Any]] = None
        if plan_id:
            try:
                plan_uuid = str(uuid.UUID(str(plan_id)))
            except (ValueError, TypeError):
                raise APIError("Field 'plan_id' must be a valid UUID.", status_code=400, code="VALIDATION_ERROR")

            plan_res = self.client.table("event_plans").select("*").eq("id", plan_uuid).execute()
            if not plan_res.data or len(plan_res.data) == 0:
                raise APIError(f"Plan with id '{plan_uuid}' not found.", status_code=404, code="NOT_FOUND")
            plan_record = plan_res.data[0]
            if str(plan_record.get("event_id")) != event_id:
                raise APIError(
                    message=f"Plan with id '{plan_uuid}' does not belong to event '{event_id}'.",
                    status_code=400,
                    code="CROSS_EVENT_REFERENCE_FORBIDDEN",
                )
            target_plan = plan_record
        else:
            # Fetch active plan if present
            active_res = self.client.table("event_plans").select("*").eq("event_id", event_id).eq("is_active", True).execute()
            if active_res.data and len(active_res.data) > 0:
                target_plan = active_res.data[0]

        # 3. Fetch related components
        pref_res = self.client.table("event_preferences").select("*").eq("event_id", event_id).execute()
        preferences = pref_res.data[0] if pref_res.data else None

        budget_items_res = self.client.table("budget_items").select("*").eq("event_id", event_id).execute()
        budget_items = budget_items_res.data or []

        venues_res = self.client.table("venues").select("*").eq("event_id", event_id).execute()
        venues = venues_res.data or []

        agenda_res = self.client.table("agenda_sessions").select("*").eq("event_id", event_id).order("start_time", desc=False).execute()
        agenda_sessions = agenda_res.data or []

        tasks_res = self.client.table("tasks").select("*").eq("event_id", event_id).order("sort_order", desc=False).execute()
        tasks = tasks_res.data or []

        # 4. Calculate budget summary using schema columns (estimated_amount, confirmed_amount, actual_amount, paid_amount)
        target_budget = float(event.get("target_budget") or 0.0)
        total_estimated = sum(
            float(i.get("estimated_amount") if i.get("estimated_amount") is not None else (i.get("estimated_cost") or 0.0))
            for i in budget_items
        )
        total_confirmed = sum(
            float(i.get("confirmed_amount") if i.get("confirmed_amount") is not None else (i.get("confirmed_cost") or 0.0))
            for i in budget_items
        )
        total_actual = sum(
            float(i.get("actual_amount") if i.get("actual_amount") is not None else (i.get("actual_cost") or 0.0))
            for i in budget_items
        )
        total_paid = sum(float(i.get("paid_amount") or 0.0) for i in budget_items)
        remaining = target_budget - total_actual

        budget_summary = {
            "target_budget": round(target_budget, 2),
            "total_estimated": round(total_estimated, 2),
            "total_confirmed": round(total_confirmed, 2),
            "total_actual": round(total_actual, 2),
            "total_paid": round(total_paid, 2),
            "remaining_budget": round(remaining, 2),
        }

        # 5. Generate deliverable file bytes
        mime_type = EXPORT_MIME_TYPES[export_type]
        ext = EXPORT_EXTENSIONS[export_type]
        export_id = str(uuid.uuid4())
        safe_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in event.get("title", "event"))
        filename = f"{safe_title}_{export_type}_{export_id[:8]}.{ext}"
        storage_path = f"exports/{event_id}/{export_id}.{ext}"

        if export_type == "pdf_summary":
            file_bytes = self.generate_pdf_summary(event, target_plan, budget_summary, agenda_sessions, venues)
        elif export_type == "ics_calendar":
            file_bytes = self.generate_ics_calendar(event, agenda_sessions)
        elif export_type == "csv_budget":
            file_bytes = self.generate_csv_budget(event, budget_items, budget_summary)
        elif export_type == "json_backup":
            file_bytes = self.generate_json_backup(event, preferences, target_plan, budget_summary, budget_items, venues, agenda_sessions, tasks)
        else:
            raise APIError("Unsupported export type.", status_code=400, code="VALIDATION_ERROR")

        file_size = len(file_bytes)

        # 6. Save to storage
        self._save_to_storage(storage_path, file_bytes, mime_type)

        # 7. Record metadata in public.plan_exports (via backend service role)
        metadata = {
            "filename": filename,
            "export_type": export_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "event_title": event.get("title"),
        }
        export_payload = {
            "id": export_id,
            "event_id": event_id,
            "plan_id": target_plan["id"] if target_plan else None,
            "export_type": export_type,
            "storage_path": storage_path,
            "file_size_bytes": file_size,
            "mime_type": mime_type,
            "metadata": metadata,
            "created_by": user_id,
        }

        try:
            res = self.client.table("plan_exports").insert(export_payload).execute()
            if not res.data or len(res.data) == 0:
                raise APIError("Failed to record export metadata.", status_code=500, code="DATABASE_ERROR")
            return res.data[0]
        except Exception as e:
            # Compensating action: Delete uploaded file from storage if metadata insertion fails
            # to prevent orphaned storage objects.
            try:
                self._delete_from_storage(storage_path)
            except Exception:
                pass

            if isinstance(e, APIError):
                raise
            self._handle_db_error(e, "generate_export")

    def list_exports(self, event_id: str) -> List[Dict[str, Any]]:
        """Lists metadata of plan exports belonging to the specified event."""
        try:
            res = (
                self.client.table("plan_exports")
                .select("*")
                .eq("event_id", event_id)
                .order("created_at", desc=True)
                .execute()
            )
            return res.data or []
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_exports")

    def get_export_metadata(self, event_id: str, export_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves export metadata enforcing event-to-export relationship."""
        try:
            res = (
                self.client.table("plan_exports")
                .select("*")
                .eq("id", export_id)
                .eq("event_id", event_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_export_metadata")

    def download_export(self, event_id: str, export_id: str) -> Tuple[bytes, str, str]:
        """Retrieves export file content, validating event association.

        Returns:
            Tuple of (file_bytes, mime_type, filename)
        """
        export_meta = self.get_export_metadata(event_id, export_id)
        if not export_meta:
            raise APIError(
                message=f"Export with id '{export_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        storage_path = export_meta["storage_path"]
        mime_type = export_meta.get("mime_type", "application/octet-stream")
        meta = export_meta.get("metadata") or {}
        filename = meta.get("filename") or f"export_{export_id}.{EXPORT_EXTENSIONS.get(export_meta.get('export_type', ''), 'bin')}"

        file_bytes = self._download_from_storage(storage_path)
        return file_bytes, mime_type, filename

    def delete_export(self, event_id: str, export_id: str) -> bool:
        """Deletes export record and file deliverable."""
        export_meta = self.get_export_metadata(event_id, export_id)
        if not export_meta:
            raise APIError(
                message=f"Export with id '{export_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        storage_path = export_meta["storage_path"]
        self._delete_from_storage(storage_path)

        try:
            res = (
                self.client.table("plan_exports")
                .delete()
                .eq("id", export_id)
                .eq("event_id", event_id)
                .execute()
            )
            return bool(res.data and len(res.data) > 0)
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_export")

    def _handle_db_error(self, e: Exception, op: str) -> None:
        """Translates database exceptions into standardized API errors."""
        err = str(e).lower()
        if "check constraint" in err or "23514" in err:
            raise APIError("Data violates export validation constraints.", status_code=400, code="VALIDATION_ERROR")
        if "foreign key" in err or "23503" in err:
            raise APIError("Referenced record does not exist or violates boundary rules.", status_code=400, code="FOREIGN_KEY_ERROR")
        if "unique" in err or "23505" in err:
            raise APIError("A unique constraint violation occurred.", status_code=409, code="CONFLICT")
        if "not configured" in err or "connection" in err:
            raise APIError("Database service is temporarily unavailable.", status_code=503, code="SERVICE_UNAVAILABLE")
        raise APIError(f"Database operation failed during {op}.", status_code=500, code="DATABASE_ERROR")
