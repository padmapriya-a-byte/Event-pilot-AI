"""EventPilot AI - Event & Preferences Service Layer.

Provides data access and business logic for events and event preferences tables,
validating inputs against the database schema constraints, enforcing ownership,
and safely translating database errors into standardized API errors.
"""

from datetime import datetime, timezone
import re
from typing import Dict, Any, List, Optional
import uuid

from ..services.supabase_service import SupabaseAdminService
from ..utils.errors import APIError

ALLOWED_EVENT_TYPES = {
    "conference",
    "wedding",
    "meetup",
    "corporate",
    "concert",
    "exhibition",
    "hackathon",
    "other",
}

ALLOWED_STATUSES = {
    "draft",
    "planning",
    "confirmed",
    "completed",
    "cancelled",
}

CURRENCY_REGEX = re.compile(r"^[A-Z]{3}$")


def parse_iso_datetime(dt_str: Any) -> datetime:
    """Parses and normalizes an ISO 8601 datetime string to a timezone-aware datetime."""
    if not isinstance(dt_str, str):
        raise APIError(
            message="Datetime value must be an ISO 8601 string.",
            status_code=400,
            code="VALIDATION_ERROR",
        )
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise APIError(
            message=f"Invalid ISO 8601 datetime format: '{dt_str}'.",
            status_code=400,
            code="VALIDATION_ERROR",
        )


class EventService:
    """Service layer managing events and event_preferences persistence."""

    def __init__(self, admin_service: Optional[SupabaseAdminService] = None):
        self._admin_service = admin_service or SupabaseAdminService()

    @property
    def client(self) -> Any:
        """Returns the administrative Supabase client instance."""
        return self._admin_service.client

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def validate_event_data(
        self,
        data: Dict[str, Any],
        is_update: bool = False,
        existing_event: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validates event input against PostgreSQL schema constraints.

        Strips protected system fields (id, owner_id, created_at, updated_at).
        """
        cleaned: Dict[str, Any] = {}

        # 1. Title validation
        if "title" in data or not is_update:
            title = data.get("title")
            if not isinstance(title, str) or len(title.strip()) < 2:
                raise APIError(
                    message="Field 'title' is required and must be at least 2 characters.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["title"] = title.strip()

        # 2. Event type validation
        if "event_type" in data or not is_update:
            event_type = data.get("event_type")
            if not isinstance(event_type, str) or event_type not in ALLOWED_EVENT_TYPES:
                allowed_str = ", ".join(sorted(ALLOWED_EVENT_TYPES))
                raise APIError(
                    message=f"Field 'event_type' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["event_type"] = event_type

        # 3. Status validation
        if "status" in data:
            status = data.get("status")
            if not isinstance(status, str) or status not in ALLOWED_STATUSES:
                allowed_str = ", ".join(sorted(ALLOWED_STATUSES))
                raise APIError(
                    message=f"Field 'status' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["status"] = status
        elif not is_update:
            cleaned["status"] = "draft"

        # 4. Dates validation
        start_date_raw = data.get("start_date") if "start_date" in data else (existing_event.get("start_date") if existing_event else None)
        end_date_raw = data.get("end_date") if "end_date" in data else (existing_event.get("end_date") if existing_event else None)

        start_dt = None
        if start_date_raw is not None:
            start_dt = parse_iso_datetime(start_date_raw)
            if "start_date" in data:
                cleaned["start_date"] = start_dt.isoformat()
        elif "start_date" in data:
            cleaned["start_date"] = None

        end_dt = None
        if end_date_raw is not None:
            end_dt = parse_iso_datetime(end_date_raw)
            if "end_date" in data:
                cleaned["end_date"] = end_dt.isoformat()
        elif "end_date" in data:
            cleaned["end_date"] = None

        if start_dt is not None and end_dt is not None:
            if end_dt < start_dt:
                raise APIError(
                    message="Field 'end_date' cannot be earlier than 'start_date'.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )

        # 5. Timezone validation
        if "timezone" in data:
            tz = data.get("timezone")
            if not isinstance(tz, str) or not tz.strip():
                raise APIError(
                    message="Field 'timezone' must be a non-empty string.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["timezone"] = tz.strip()
        elif not is_update:
            cleaned["timezone"] = "UTC"

        # 6. Expected attendees validation
        if "expected_attendees" in data:
            attendees = data.get("expected_attendees")
            if attendees is not None:
                if type(attendees) is not int or attendees < 0:
                    raise APIError(
                        message="Field 'expected_attendees' must be a non-negative integer or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
            cleaned["expected_attendees"] = attendees

        # 7. Currency validation
        if "currency" in data:
            curr = data.get("currency")
            if not isinstance(curr, str) or not CURRENCY_REGEX.match(curr):
                raise APIError(
                    message="Field 'currency' must be an uppercase 3-letter ISO code (e.g. 'USD').",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["currency"] = curr
        elif not is_update:
            cleaned["currency"] = "USD"

        # 8. Target budget validation
        if "target_budget" in data:
            budget = data.get("target_budget")
            if budget is not None:
                try:
                    budget_float = float(budget)
                    if budget_float < 0:
                        raise ValueError()
                    cleaned["target_budget"] = round(budget_float, 2)
                except (ValueError, TypeError):
                    raise APIError(
                        message="Field 'target_budget' must be a non-negative number or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
            else:
                cleaned["target_budget"] = None

        # 9. Description
        if "description" in data:
            desc = data.get("description")
            if desc is not None and not isinstance(desc, str):
                raise APIError(
                    message="Field 'description' must be a string or null.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["description"] = desc

        # 10. Archived flag
        if "is_archived" in data:
            archived = data.get("is_archived")
            if type(archived) is not bool:
                raise APIError(
                    message="Field 'is_archived' must be a boolean.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["is_archived"] = archived
        elif not is_update:
            cleaned["is_archived"] = False

        return cleaned

    def validate_preferences_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates event preferences data against schema constraints."""
        cleaned: Dict[str, Any] = {}

        if "vibe_style" in data:
            vibe = data.get("vibe_style")
            if not isinstance(vibe, list) or not all(isinstance(v, str) for v in vibe):
                raise APIError(
                    message="Field 'vibe_style' must be a list of strings.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["vibe_style"] = vibe

        if "catering_preferences" in data:
            catering = data.get("catering_preferences")
            if not isinstance(catering, dict):
                raise APIError(
                    message="Field 'catering_preferences' must be a JSON object.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["catering_preferences"] = catering

        if "accessibility_requirements" in data:
            access = data.get("accessibility_requirements")
            if not isinstance(access, list) or not all(isinstance(a, str) for a in access):
                raise APIError(
                    message="Field 'accessibility_requirements' must be a list of strings.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["accessibility_requirements"] = access

        if "target_audience" in data:
            aud = data.get("target_audience")
            if aud is not None and not isinstance(aud, str):
                raise APIError(
                    message="Field 'target_audience' must be a string or null.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["target_audience"] = aud

        if "ai_generation_parameters" in data:
            ai_params = data.get("ai_generation_parameters")
            if not isinstance(ai_params, dict):
                raise APIError(
                    message="Field 'ai_generation_parameters' must be a JSON object.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["ai_generation_parameters"] = ai_params

        if "custom_constraints" in data:
            constraints = data.get("custom_constraints")
            if not isinstance(constraints, list):
                raise APIError(
                    message="Field 'custom_constraints' must be a JSON list.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["custom_constraints"] = constraints

        return cleaned

    # =========================================================================
    # Event Operations
    # =========================================================================

    def create_event(self, owner_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new event and initializes its default preferences row."""
        # Enforce server-side ownership: ignore any client-supplied owner_id
        validated_data = self.validate_event_data(data, is_update=False)
        validated_data["owner_id"] = owner_id

        try:
            # 1. Insert event record
            res = self.client.table("events").insert(validated_data).execute()
            if not res.data or len(res.data) == 0:
                raise APIError(
                    message="Failed to create event in database.",
                    status_code=500,
                    code="DATABASE_ERROR",
                )
            created_event = res.data[0]
            event_id = created_event["id"]

            # 2. Automatically initialize default preferences for the new event
            default_pref = {
                "event_id": event_id,
                "vibe_style": [],
                "catering_preferences": {},
                "accessibility_requirements": [],
                "target_audience": None,
                "ai_generation_parameters": {
                    "temperature": 0.7,
                    "model": "gemini-2.5-flash",
                },
                "custom_constraints": [],
            }
            try:
                self.client.table("event_preferences").insert(default_pref).execute()
            except Exception:
                # Preferences initialization failure should not block event creation
                pass

            return created_event

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "create_event")

    def list_events(
        self,
        owner_id: str,
        status: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lists events owned strictly by owner_id with optional status/archived filtering."""
        try:
            query = self.client.table("events").select("*").eq("owner_id", owner_id)

            if status:
                if status not in ALLOWED_STATUSES:
                    raise APIError(
                        message=f"Invalid filter status '{status}'.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                query = query.eq("status", status)

            if not include_archived:
                query = query.eq("is_archived", False)

            query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
            res = query.execute()
            return res.data or []

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_events")

    def get_event(self, event_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single event ensuring owner_id match."""
        try:
            res = (
                self.client.table("events")
                .select("*")
                .eq("id", event_id)
                .eq("owner_id", owner_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_event")

    def update_event(
        self,
        event_id: str,
        owner_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Updates fields of an event owned by owner_id."""
        existing = self.get_event(event_id, owner_id)
        if not existing:
            raise APIError(
                message=f"Event with id '{event_id}' not found.",
                status_code=404,
                code="NOT_FOUND",
            )

        validated_updates = self.validate_event_data(
            data,
            is_update=True,
            existing_event=existing,
        )

        if not validated_updates:
            return existing

        try:
            res = (
                self.client.table("events")
                .update(validated_updates)
                .eq("id", event_id)
                .eq("owner_id", owner_id)
                .execute()
            )
            if not res.data or len(res.data) == 0:
                raise APIError(
                    message=f"Event with id '{event_id}' not found or update failed.",
                    status_code=404,
                    code="NOT_FOUND",
                )
            return res.data[0]

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "update_event")

    def delete_event(self, event_id: str, owner_id: str) -> bool:
        """Deletes an event owned by owner_id."""
        try:
            res = (
                self.client.table("events")
                .delete()
                .eq("id", event_id)
                .eq("owner_id", owner_id)
                .execute()
            )
            return bool(res.data and len(res.data) > 0)

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_event")

    # =========================================================================
    # Preferences Operations
    # =========================================================================

    def get_preferences(self, event_id: str) -> Dict[str, Any]:
        """Retrieves preferences for an event, initializing defaults if none exist."""
        try:
            res = (
                self.client.table("event_preferences")
                .select("*")
                .eq("event_id", event_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]

            # Lazy initialize default preferences if missing
            default_pref = {
                "event_id": event_id,
                "vibe_style": [],
                "catering_preferences": {},
                "accessibility_requirements": [],
                "target_audience": None,
                "ai_generation_parameters": {
                    "temperature": 0.7,
                    "model": "gemini-2.5-flash",
                },
                "custom_constraints": [],
            }
            insert_res = (
                self.client.table("event_preferences")
                .insert(default_pref)
                .execute()
            )
            if insert_res.data and len(insert_res.data) > 0:
                return insert_res.data[0]
            return default_pref

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_preferences")

    def update_preferences(
        self,
        event_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Updates preferences for an event (upsert behavior)."""
        validated_data = self.validate_preferences_data(data)

        try:
            # Check if preferences record exists
            existing_res = (
                self.client.table("event_preferences")
                .select("id")
                .eq("event_id", event_id)
                .execute()
            )

            if existing_res.data and len(existing_res.data) > 0:
                # Update existing
                res = (
                    self.client.table("event_preferences")
                    .update(validated_data)
                    .eq("event_id", event_id)
                    .execute()
                )
            else:
                # Create with defaults merged
                insert_payload = {
                    "event_id": event_id,
                    "vibe_style": validated_data.get("vibe_style", []),
                    "catering_preferences": validated_data.get("catering_preferences", {}),
                    "accessibility_requirements": validated_data.get("accessibility_requirements", []),
                    "target_audience": validated_data.get("target_audience", None),
                    "ai_generation_parameters": validated_data.get(
                        "ai_generation_parameters",
                        {"temperature": 0.7, "model": "gemini-2.5-flash"},
                    ),
                    "custom_constraints": validated_data.get("custom_constraints", []),
                }
                res = (
                    self.client.table("event_preferences")
                    .insert(insert_payload)
                    .execute()
                )

            if not res.data or len(res.data) == 0:
                raise APIError(
                    message="Failed to update event preferences.",
                    status_code=500,
                    code="DATABASE_ERROR",
                )
            return res.data[0]

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "update_preferences")

    # =========================================================================
    # Error Handling
    # =========================================================================

    def _handle_db_error(self, e: Exception, operation: str) -> None:
        """Translates Supabase/Postgrest errors into standardized APIErrors."""
        error_str = str(e)

        # Check for Postgrest constraint violation
        if "check constraint" in error_str.lower() or "23514" in error_str:
            raise APIError(
                message="Data violates event validation constraints.",
                status_code=400,
                code="VALIDATION_ERROR",
            )
        if "foreign key" in error_str.lower() or "23503" in error_str:
            raise APIError(
                message="Referenced profile or event does not exist.",
                status_code=400,
                code="FOREIGN_KEY_ERROR",
            )
        if "duplicate key" in error_str.lower() or "23505" in error_str:
            raise APIError(
                message="A record with these unique identifiers already exists.",
                status_code=409,
                code="CONFLICT",
            )

        # Catch service unconfigured or connection errors
        if "not configured" in error_str.lower() or "connection" in error_str.lower():
            raise APIError(
                message="Database service is temporarily unavailable.",
                status_code=503,
                code="SERVICE_UNAVAILABLE",
            )

        # Default clean database error: never leak connection strings or stack traces
        raise APIError(
            message=f"Database operation failed during {operation}.",
            status_code=500,
            code="DATABASE_ERROR",
        )
