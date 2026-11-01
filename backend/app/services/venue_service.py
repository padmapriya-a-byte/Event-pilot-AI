"""EventPilot AI - Venue & Agenda Session Service Layer.

Provides data access and validation for venues and agenda sessions, enforcing:
  - Single selected venue invariant per event.
  - Cross-event venue reference prevention on agenda sessions.
  - Positive capacity and non-negative rental costs.
  - Valid session time ranges (end_time > start_time).
  - Sanitized database error handling.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid

from ..services.supabase_service import SupabaseAdminService, create_user_client
from ..utils.errors import APIError

ALLOWED_VENUE_STATUSES = {
    "shortlisted",
    "viewing_scheduled",
    "proposal_received",
    "selected",
    "rejected",
}

ALLOWED_SESSION_TYPES = {
    "keynote",
    "panel",
    "workshop",
    "presentation",
    "break",
    "networking",
    "ceremony",
    "other",
}


def parse_timestamp(val: Any, field_name: str) -> datetime:
    """Parses an ISO 8601 string into a timezone-aware UTC datetime."""
    if not isinstance(val, str):
        raise APIError(
            message=f"Field '{field_name}' must be an ISO 8601 string.",
            status_code=400,
            code="VALIDATION_ERROR",
        )
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise APIError(
            message=f"Invalid ISO 8601 datetime format for '{field_name}': '{val}'.",
            status_code=400,
            code="VALIDATION_ERROR",
        )


class VenueService:
    """Service layer managing venues and agenda sessions."""

    _event_locks: Dict[str, threading.Lock] = {}
    _global_lock = threading.Lock()

    def __init__(self, admin_service: Optional[SupabaseAdminService] = None):
        self._admin_service = admin_service or SupabaseAdminService()

    @classmethod
    def _get_event_lock(cls, event_id: str) -> threading.Lock:
        """Retrieves or creates a thread lock for an event to prevent in-process selection races."""
        with cls._global_lock:
            if event_id not in cls._event_locks:
                cls._event_locks[event_id] = threading.Lock()
            return cls._event_locks[event_id]

    @property
    def client(self) -> Any:
        return self._admin_service.client

    def _get_rpc_client(self, user_token: Optional[str] = None) -> Any:
        """Returns a request-scoped Supabase client for user-authenticated RPC calls.

        Uses the authenticated caller's JWT so PostgreSQL auth.uid() and auth.is_event_owner()
        succeed without mutating the shared administrative Supabase client.
        """
        if user_token:
            if hasattr(self._admin_service, "get_user_client"):
                return self._admin_service.get_user_client(user_token)
            elif hasattr(self._admin_service, "create_user_client"):
                return self._admin_service.create_user_client(user_token)
            else:
                try:
                    return create_user_client(user_token)
                except Exception:
                    return self.client
        return self.client

    # =========================================================================
    # Venue Validation & Operations
    # =========================================================================

    def validate_venue_data(self, data: Dict[str, Any], is_update: bool = False) -> Dict[str, Any]:
        """Validates venue payload against PostgreSQL schema constraints."""
        cleaned: Dict[str, Any] = {}

        if "name" in data or not is_update:
            name = data.get("name")
            if not isinstance(name, str) or len(name.strip()) < 1:
                raise APIError(
                    message="Field 'name' is required and cannot be empty.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["name"] = name.strip()

        for str_field in ("address", "city", "state_province", "country", "postal_code", "contact_name", "contact_email", "contact_phone", "notes"):
            if str_field in data:
                val = data.get(str_field)
                if val is not None and not isinstance(val, str):
                    raise APIError(
                        message=f"Field '{str_field}' must be a string or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                cleaned[str_field] = val.strip() if isinstance(val, str) else None

        if "capacity" in data:
            cap = data.get("capacity")
            if cap is not None:
                if type(cap) is not int or cap <= 0:
                    raise APIError(
                        message="Field 'capacity' must be a positive integer or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
            cleaned["capacity"] = cap

        if "rental_cost" in data:
            cost = data.get("rental_cost")
            if cost is not None:
                try:
                    cost_flt = float(cost)
                    if cost_flt < 0:
                        raise ValueError()
                    cleaned["rental_cost"] = round(cost_flt, 2)
                except (ValueError, TypeError):
                    raise APIError(
                        message="Field 'rental_cost' must be a non-negative number or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
            else:
                cleaned["rental_cost"] = None

        if "amenities" in data:
            amenities = data.get("amenities")
            if not isinstance(amenities, list) or not all(isinstance(a, str) for a in amenities):
                raise APIError(
                    message="Field 'amenities' must be a list of strings.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["amenities"] = amenities
        elif not is_update:
            cleaned["amenities"] = []

        if "status" in data:
            status = data.get("status")
            if not isinstance(status, str) or status not in ALLOWED_VENUE_STATUSES:
                allowed_str = ", ".join(sorted(ALLOWED_VENUE_STATUSES))
                raise APIError(
                    message=f"Field 'status' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["status"] = status
        elif not is_update:
            cleaned["status"] = "shortlisted"

        if "is_selected" in data:
            sel = data.get("is_selected")
            if type(sel) is not bool:
                raise APIError(
                    message="Field 'is_selected' must be a boolean.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["is_selected"] = sel
        elif not is_update:
            cleaned["is_selected"] = False

        return cleaned

    def create_venue(
        self,
        event_id: str,
        data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a venue for an event. Enforces at most one selected venue under concurrency."""
        if user_token is None:
            try:
                from flask import g, has_request_context
                if has_request_context():
                    user_token = getattr(g, "token", None)
            except ImportError:
                pass

        validated = self.validate_venue_data(data, is_update=False)
        validated["event_id"] = event_id

        if not validated.get("is_selected"):
            try:
                res = self.client.table("venues").insert(validated).execute()
                if not res.data or len(res.data) == 0:
                    raise APIError("Failed to create venue in database.", status_code=500, code="DATABASE_ERROR")
                return res.data[0]
            except APIError:
                raise
            except Exception as e:
                self._handle_db_error(e, "create_venue")

        # When creating a venue with is_selected = True:
        # Synchronize per-event and retry on constraint conflict to prevent concurrency races
        lock = self._get_event_lock(event_id)
        with lock:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Unselect any currently selected venue in this event first
                    self.client.table("venues").update({"is_selected": False}).eq("event_id", event_id).eq("is_selected", True).execute()

                    res = self.client.table("venues").insert(validated).execute()
                    if not res.data or len(res.data) == 0:
                        raise APIError("Failed to create venue in database.", status_code=500, code="DATABASE_ERROR")
                    return res.data[0]
                except APIError:
                    raise
                except Exception as e:
                    err = str(e).lower()
                    if ("unique" in err or "23505" in err) and attempt < max_retries - 1:
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    self._handle_db_error(e, "create_venue")

    def list_venues(self, event_id: str) -> List[Dict[str, Any]]:
        """Lists all venues belonging to the specified event."""
        try:
            res = self.client.table("venues").select("*").eq("event_id", event_id).order("created_at", desc=False).execute()
            return res.data or []
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_venues")

    def get_venue(self, event_id: str, venue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single venue ensuring event-to-venue association."""
        try:
            res = self.client.table("venues").select("*").eq("id", venue_id).eq("event_id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_venue")

    def update_venue(
        self,
        event_id: str,
        venue_id: str,
        data: Dict[str, Any],
        user_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates a venue. Enforces single selected venue invariant under concurrency."""
        if user_token is None:
            try:
                from flask import g, has_request_context
                if has_request_context():
                    user_token = getattr(g, "token", None)
            except ImportError:
                pass

        existing = self.get_venue(event_id, venue_id)
        if not existing:
            raise APIError(f"Venue with id '{venue_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

        validated = self.validate_venue_data(data, is_update=True)
        if not validated:
            return existing

        is_selecting = validated.get("is_selected") is True

        if not is_selecting:
            try:
                res = self.client.table("venues").update(validated).eq("id", venue_id).eq("event_id", event_id).execute()
                if not res.data or len(res.data) == 0:
                    raise APIError("Failed to update venue.", status_code=500, code="DATABASE_ERROR")
                return res.data[0]
            except APIError:
                raise
            except Exception as e:
                self._handle_db_error(e, "update_venue")

        # When setting is_selected = True:
        # Attempt atomic database RPC if available; fallback to synchronized update with retry
        lock = self._get_event_lock(event_id)
        with lock:
            # 1. Try atomic database RPC via request-scoped user client
            rpc_client = self._get_rpc_client(user_token)
            if hasattr(rpc_client, "rpc"):
                try:
                    rpc_res = rpc_client.rpc(
                        "select_event_venue",
                        {"p_event_id": event_id, "p_venue_id": venue_id},
                    ).execute()
                    if rpc_res.data:
                        base_venue = rpc_res.data[0] if isinstance(rpc_res.data, list) else rpc_res.data
                        # If additional fields were provided, update them
                        extra_fields = {k: v for k, v in validated.items() if k not in ("is_selected", "status")}
                        if extra_fields:
                            res = self.client.table("venues").update(extra_fields).eq("id", venue_id).eq("event_id", event_id).execute()
                            return res.data[0] if res.data else base_venue
                        return base_venue
                except APIError:
                    raise
                except Exception as e:
                    err_msg = str(e).lower()
                    if "forbidden" in err_msg or ("42501" in err_msg and "caller does not own event" in err_msg):
                        raise APIError(
                            message="Forbidden: You do not have permission to select venues for this event.",
                            status_code=403,
                            code="FORBIDDEN",
                        )
                    # Stored procedure not installed or transient failure, fallback to synchronized table update
                    pass

            # 2. Fallback: synchronized unselect-and-select with conflict retry
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Demote any other currently selected venue
                    self.client.table("venues").update({"is_selected": False}).eq("event_id", event_id).eq("is_selected", True).execute()

                    # Promote target venue to selected
                    res = self.client.table("venues").update(validated).eq("id", venue_id).eq("event_id", event_id).execute()
                    if not res.data or len(res.data) == 0:
                        raise APIError("Failed to update venue.", status_code=500, code="DATABASE_ERROR")
                    return res.data[0]
                except APIError:
                    raise
                except Exception as e:
                    err = str(e).lower()
                    if ("unique" in err or "23505" in err) and attempt < max_retries - 1:
                        time.sleep(0.01 * (attempt + 1))
                        continue
                    self._handle_db_error(e, "update_venue")

    def delete_venue(self, event_id: str, venue_id: str) -> bool:
        """Deletes a venue belonging to the event."""
        existing = self.get_venue(event_id, venue_id)
        if not existing:
            raise APIError(f"Venue with id '{venue_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

        try:
            res = self.client.table("venues").delete().eq("id", venue_id).eq("event_id", event_id).execute()
            return bool(res.data and len(res.data) > 0)
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_venue")

    # =========================================================================
    # Agenda Session Validation & Operations
    # =========================================================================

    def validate_session_data(
        self,
        event_id: str,
        data: Dict[str, Any],
        is_update: bool = False,
        existing_session: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validates agenda session payload against schema constraints and cross-event venue boundaries."""
        cleaned: Dict[str, Any] = {}

        if "title" in data or not is_update:
            title = data.get("title")
            if not isinstance(title, str) or len(title.strip()) < 1:
                raise APIError(
                    message="Field 'title' is required and cannot be empty.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["title"] = title.strip()

        for str_field in ("description", "speaker_facilitator", "room_location"):
            if str_field in data:
                val = data.get(str_field)
                if val is not None and not isinstance(val, str):
                    raise APIError(
                        message=f"Field '{str_field}' must be a string or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                cleaned[str_field] = val.strip() if isinstance(val, str) else None

        # Session times: end_time must be strictly greater than start_time
        start_val = data.get("start_time") if "start_time" in data else (existing_session.get("start_time") if existing_session else None)
        end_val = data.get("end_time") if "end_time" in data else (existing_session.get("end_time") if existing_session else None)

        if not is_update and (start_val is None or end_val is None):
            raise APIError(
                message="Fields 'start_time' and 'end_time' are required.",
                status_code=400,
                code="VALIDATION_ERROR",
            )

        start_dt = None
        if start_val is not None:
            start_dt = parse_timestamp(start_val, "start_time")
            if "start_time" in data:
                cleaned["start_time"] = start_dt.isoformat()

        end_dt = None
        if end_val is not None:
            end_dt = parse_timestamp(end_val, "end_time")
            if "end_time" in data:
                cleaned["end_time"] = end_dt.isoformat()

        if start_dt is not None and end_dt is not None:
            if end_dt <= start_dt:
                raise APIError(
                    message="Field 'end_time' must be strictly after 'start_time'.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )

        if "session_type" in data:
            stype = data.get("session_type")
            if not isinstance(stype, str) or stype not in ALLOWED_SESSION_TYPES:
                allowed_str = ", ".join(sorted(ALLOWED_SESSION_TYPES))
                raise APIError(
                    message=f"Field 'session_type' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["session_type"] = stype
        elif not is_update:
            cleaned["session_type"] = "presentation"

        if "sort_order" in data:
            so = data.get("sort_order")
            if type(so) is not int:
                raise APIError(
                    message="Field 'sort_order' must be an integer.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["sort_order"] = so
        elif not is_update:
            cleaned["sort_order"] = 0

        # Venue Boundary Check: If venue_id is provided, verify it belongs to this event!
        if "venue_id" in data:
            venue_id = data.get("venue_id")
            if venue_id is not None:
                try:
                    uuid_str = str(uuid.UUID(str(venue_id)))
                except (ValueError, TypeError):
                    raise APIError(
                        message="Field 'venue_id' must be a valid UUID or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                # Verify venue belongs to event_id
                target_venue = self.get_venue(event_id, uuid_str)
                if not target_venue:
                    raise APIError(
                        message=f"Venue with id '{uuid_str}' does not belong to event '{event_id}'.",
                        status_code=400,
                        code="CROSS_EVENT_REFERENCE_FORBIDDEN",
                    )
                cleaned["venue_id"] = uuid_str
            else:
                cleaned["venue_id"] = None

        return cleaned

    def create_session(self, event_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates an agenda session bound to event_id."""
        validated = self.validate_session_data(event_id, data, is_update=False)
        validated["event_id"] = event_id

        try:
            res = self.client.table("agenda_sessions").insert(validated).execute()
            if not res.data or len(res.data) == 0:
                raise APIError("Failed to create agenda session.", status_code=500, code="DATABASE_ERROR")
            return res.data[0]
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "create_session")

    def list_sessions(self, event_id: str) -> List[Dict[str, Any]]:
        """Lists agenda sessions for an event ordered by start_time and sort_order."""
        try:
            res = self.client.table("agenda_sessions").select("*").eq("event_id", event_id).order("start_time", desc=False).order("sort_order", desc=False).execute()
            return res.data or []
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_sessions")

    def get_session(self, event_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves an agenda session enforcing event association."""
        try:
            res = self.client.table("agenda_sessions").select("*").eq("id", session_id).eq("event_id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_session")

    def update_session(self, event_id: str, session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an agenda session enforcing event association and boundary checks."""
        existing = self.get_session(event_id, session_id)
        if not existing:
            raise APIError(f"Agenda session with id '{session_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

        validated = self.validate_session_data(event_id, data, is_update=True, existing_session=existing)
        if not validated:
            return existing

        try:
            res = self.client.table("agenda_sessions").update(validated).eq("id", session_id).eq("event_id", event_id).execute()
            if not res.data or len(res.data) == 0:
                raise APIError("Failed to update agenda session.", status_code=500, code="DATABASE_ERROR")
            return res.data[0]
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "update_session")

    def delete_session(self, event_id: str, session_id: str) -> bool:
        """Deletes an agenda session belonging to the event."""
        existing = self.get_session(event_id, session_id)
        if not existing:
            raise APIError(f"Agenda session with id '{session_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

        try:
            res = self.client.table("agenda_sessions").delete().eq("id", session_id).eq("event_id", event_id).execute()
            return bool(res.data and len(res.data) > 0)
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_session")

    def _handle_db_error(self, e: Exception, op: str) -> None:
        err = str(e).lower()
        if "check constraint" in err or "23514" in err:
            raise APIError("Data violates venue or agenda validation constraints.", status_code=400, code="VALIDATION_ERROR")
        if "foreign key" in err or "23503" in err:
            raise APIError("Referenced record does not exist or violates boundary rules.", status_code=400, code="FOREIGN_KEY_ERROR")
        if "unique" in err or "23505" in err:
            raise APIError("At most one selected venue is permitted per event.", status_code=409, code="CONFLICT")
        if "not configured" in err or "connection" in err:
            raise APIError("Database service is temporarily unavailable.", status_code=503, code="SERVICE_UNAVAILABLE")
        raise APIError(f"Database operation failed during {op}.", status_code=500, code="DATABASE_ERROR")
