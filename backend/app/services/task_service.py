"""EventPilot AI - Task Management Service Layer.

Provides data access and validation for event tasks, enforcing:
  - Allowed status values ('todo', 'in_progress', 'review', 'completed', 'blocked').
  - Allowed priority values ('low', 'medium', 'high', 'urgent').
  - Composite foreign key boundary: tasks cannot reference a plan belonging to another event.
  - Sanitized database error handling.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid

from ..services.supabase_service import SupabaseAdminService
from ..utils.errors import APIError

ALLOWED_TASK_STATUSES = {
    "todo",
    "in_progress",
    "review",
    "completed",
    "blocked",
}

ALLOWED_TASK_PRIORITIES = {
    "low",
    "medium",
    "high",
    "urgent",
}


def parse_iso_datetime(dt_str: Any, field_name: str = "due_date") -> datetime:
    """Parses an ISO 8601 datetime string to a timezone-aware datetime."""
    if not isinstance(dt_str, str):
        raise APIError(
            message=f"Field '{field_name}' must be an ISO 8601 string.",
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
            message=f"Invalid ISO 8601 datetime format for '{field_name}': '{dt_str}'.",
            status_code=400,
            code="VALIDATION_ERROR",
        )


class TaskService:
    """Service layer managing tasks persistence and boundary enforcement."""

    def __init__(self, admin_service: Optional[SupabaseAdminService] = None):
        self._admin_service = admin_service or SupabaseAdminService()

    @property
    def client(self) -> Any:
        """Returns administrative Supabase client."""
        return self._admin_service.client

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def validate_task_data(
        self,
        event_id: str,
        data: Dict[str, Any],
        is_update: bool = False,
    ) -> Dict[str, Any]:
        """Validates task payload against schema constraints and cross-event plan boundaries."""
        cleaned: Dict[str, Any] = {}

        # 1. Title validation
        if "title" in data or not is_update:
            title = data.get("title")
            if not isinstance(title, str) or len(title.strip()) < 1:
                raise APIError(
                    message="Field 'title' is required and cannot be empty.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["title"] = title.strip()

        # 2. Description
        if "description" in data:
            desc = data.get("description")
            if desc is not None and not isinstance(desc, str):
                raise APIError(
                    message="Field 'description' must be a string or null.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["description"] = desc.strip() if isinstance(desc, str) else None
        elif not is_update:
            cleaned["description"] = None

        # 3. Status validation
        if "status" in data:
            status = data.get("status")
            if not isinstance(status, str) or status not in ALLOWED_TASK_STATUSES:
                allowed_str = ", ".join(sorted(ALLOWED_TASK_STATUSES))
                raise APIError(
                    message=f"Field 'status' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["status"] = status
        elif not is_update:
            cleaned["status"] = "todo"

        # 4. Priority validation
        if "priority" in data:
            priority = data.get("priority")
            if not isinstance(priority, str) or priority not in ALLOWED_TASK_PRIORITIES:
                allowed_str = ", ".join(sorted(ALLOWED_TASK_PRIORITIES))
                raise APIError(
                    message=f"Field 'priority' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["priority"] = priority
        elif not is_update:
            cleaned["priority"] = "medium"

        # 5. Due date
        if "due_date" in data:
            due_raw = data.get("due_date")
            if due_raw is not None:
                due_dt = parse_iso_datetime(due_raw, "due_date")
                cleaned["due_date"] = due_dt.isoformat()
            else:
                cleaned["due_date"] = None
        elif not is_update:
            cleaned["due_date"] = None

        # 6. Assigned to (UUID format check)
        if "assigned_to" in data:
            assigned = data.get("assigned_to")
            if assigned is not None:
                try:
                    cleaned["assigned_to"] = str(uuid.UUID(str(assigned)))
                except (ValueError, TypeError):
                    raise APIError(
                        message="Field 'assigned_to' must be a valid UUID or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
            else:
                cleaned["assigned_to"] = None
        elif not is_update:
            cleaned["assigned_to"] = None

        # 7. Category
        if "category" in data:
            cat = data.get("category")
            if cat is not None and not isinstance(cat, str):
                raise APIError(
                    message="Field 'category' must be a string or null.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["category"] = cat.strip() if isinstance(cat, str) else None
        elif not is_update:
            cleaned["category"] = None

        # 8. Sort order
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

        # 9. Plan boundary enforcement (Composite FK check)
        if "plan_id" in data:
            plan_id = data.get("plan_id")
            if plan_id is not None:
                try:
                    plan_uuid = str(uuid.UUID(str(plan_id)))
                except (ValueError, TypeError):
                    raise APIError(
                        message="Field 'plan_id' must be a valid UUID or null.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                # Verify that the plan belongs to the same event
                plan = self._get_plan_for_event(event_id, plan_uuid)
                if not plan:
                    raise APIError(
                        message=f"Plan with id '{plan_uuid}' does not belong to event '{event_id}'.",
                        status_code=400,
                        code="CROSS_EVENT_REFERENCE_FORBIDDEN",
                    )
                cleaned["plan_id"] = plan_uuid
            else:
                cleaned["plan_id"] = None
        elif not is_update:
            cleaned["plan_id"] = None

        return cleaned

    def _get_plan_for_event(self, event_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
        """Checks if a plan exists and belongs to the given event."""
        try:
            res = (
                self.client.table("event_plans")
                .select("id, event_id")
                .eq("id", plan_id)
                .eq("event_id", event_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except Exception as e:
            self._handle_db_error(e, "_get_plan_for_event")

    # =========================================================================
    # Task Operations
    # =========================================================================

    def create_task(self, event_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new task bound to the event."""
        validated = self.validate_task_data(event_id, data, is_update=False)
        validated["event_id"] = event_id

        try:
            res = self.client.table("tasks").insert(validated).execute()
            if not res.data or len(res.data) == 0:
                raise APIError("Failed to create task in database.", status_code=500, code="DATABASE_ERROR")
            return res.data[0]
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "create_task")

    def list_tasks(
        self,
        event_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lists tasks belonging to the event with optional filtering."""
        try:
            query = self.client.table("tasks").select("*").eq("event_id", event_id)

            if status:
                if status not in ALLOWED_TASK_STATUSES:
                    raise APIError(
                        message=f"Invalid filter status '{status}'.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                query = query.eq("status", status)

            if priority:
                if priority not in ALLOWED_TASK_PRIORITIES:
                    raise APIError(
                        message=f"Invalid filter priority '{priority}'.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                query = query.eq("priority", priority)

            query = query.order("sort_order", desc=False).order("created_at", desc=False).range(offset, offset + limit - 1)
            res = query.execute()
            return res.data or []
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_tasks")

    def get_task(self, event_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single task ensuring event-to-task association."""
        try:
            res = self.client.table("tasks").select("*").eq("id", task_id).eq("event_id", event_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_task")

    def update_task(self, event_id: str, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates a task belonging to the event."""
        existing = self.get_task(event_id, task_id)
        if not existing:
            raise APIError(
                message=f"Task with id '{task_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        validated = self.validate_task_data(event_id, data, is_update=True)
        if not validated:
            return existing

        try:
            res = self.client.table("tasks").update(validated).eq("id", task_id).eq("event_id", event_id).execute()
            if not res.data or len(res.data) == 0:
                raise APIError("Failed to update task.", status_code=500, code="DATABASE_ERROR")
            return res.data[0]
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "update_task")

    def delete_task(self, event_id: str, task_id: str) -> bool:
        """Deletes a task belonging to the event."""
        existing = self.get_task(event_id, task_id)
        if not existing:
            raise APIError(
                message=f"Task with id '{task_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        try:
            res = self.client.table("tasks").delete().eq("id", task_id).eq("event_id", event_id).execute()
            return bool(res.data and len(res.data) > 0)
        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_task")

    def _handle_db_error(self, e: Exception, op: str) -> None:
        """Translates database exceptions into standardized API errors."""
        err = str(e).lower()
        if "check constraint" in err or "23514" in err:
            raise APIError("Data violates task validation constraints.", status_code=400, code="VALIDATION_ERROR")
        if "foreign key" in err or "23503" in err:
            raise APIError("Referenced record does not exist or violates boundary rules.", status_code=400, code="FOREIGN_KEY_ERROR")
        if "unique" in err or "23505" in err:
            raise APIError("A unique constraint violation occurred.", status_code=409, code="CONFLICT")
        if "not configured" in err or "connection" in err:
            raise APIError("Database service is temporarily unavailable.", status_code=503, code="SERVICE_UNAVAILABLE")
        raise APIError(f"Database operation failed during {op}.", status_code=500, code="DATABASE_ERROR")
