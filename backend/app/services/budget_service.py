"""EventPilot AI - Budget Service Layer.

Provides data access and business logic for budget items and budget summary views,
enforcing monetary precision, valid categories/statuses, event-item association,
and strict distinction between estimated, confirmed, actual, and paid amounts.
"""

from datetime import date, datetime
from typing import Dict, Any, List, Optional
import uuid

from ..services.supabase_service import SupabaseAdminService
from ..utils.errors import APIError

ALLOWED_BUDGET_CATEGORIES = {
    "venue",
    "catering",
    "av_production",
    "entertainment",
    "marketing",
    "staffing",
    "transportation",
    "decor",
    "permits",
    "contingency",
    "other",
}

ALLOWED_PAYMENT_STATUSES = {
    "unpaid",
    "partially_paid",
    "paid",
    "cancelled",
}

# PostgreSQL numeric(12, 2) maximum allowable value: 9,999,999,999.99
MAX_MONETARY_AMOUNT = 9_999_999_999.99


def parse_due_date(val: Any) -> Optional[str]:
    """Parses and validates a date value into a YYYY-MM-DD string."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, str):
        trimmed = val.strip()
        if not trimmed:
            return None
        try:
            # Handle standard YYYY-MM-DD or ISO 8601 timestamps
            if "T" in trimmed:
                dt = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
                return dt.date().isoformat()
            d = date.fromisoformat(trimmed)
            return d.isoformat()
        except Exception:
            raise APIError(
                message=f"Invalid due_date format: '{val}'. Expected 'YYYY-MM-DD'.",
                status_code=400,
                code="VALIDATION_ERROR",
            )
    raise APIError(
        message="Field 'due_date' must be a date string in 'YYYY-MM-DD' format or null.",
        status_code=400,
        code="VALIDATION_ERROR",
    )


def validate_monetary_amount(field_name: str, val: Any) -> float:
    """Validates and bounds monetary amounts to non-negative numeric(12, 2)."""
    if val is None:
        return 0.00
    if type(val) is bool:
        raise APIError(
            message=f"Field '{field_name}' must be a valid number, not boolean.",
            status_code=400,
            code="VALIDATION_ERROR",
        )
    try:
        amount = float(val)
    except (ValueError, TypeError):
        raise APIError(
            message=f"Field '{field_name}' must be a valid numeric value.",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    if amount < 0:
        raise APIError(
            message=f"Field '{field_name}' cannot be negative.",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    if amount > MAX_MONETARY_AMOUNT:
        raise APIError(
            message=f"Field '{field_name}' exceeds maximum allowed numeric limit (9,999,999,999.99).",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    return round(amount, 2)


class BudgetService:
    """Service layer managing budget items and event budget aggregation summaries."""

    def __init__(self, admin_service: Optional[SupabaseAdminService] = None):
        self._admin_service = admin_service or SupabaseAdminService()

    @property
    def client(self) -> Any:
        """Returns the administrative Supabase client instance."""
        return self._admin_service.client

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_budget_item_data(
        self,
        data: Dict[str, Any],
        is_update: bool = False,
    ) -> Dict[str, Any]:
        """Validates budget item inputs against PostgreSQL constraints.

        Strips system-managed fields (id, event_id, created_at, updated_at).
        """
        cleaned: Dict[str, Any] = {}

        # 1. Category validation
        if "category" in data or not is_update:
            category = data.get("category")
            if not isinstance(category, str) or category not in ALLOWED_BUDGET_CATEGORIES:
                allowed_str = ", ".join(sorted(ALLOWED_BUDGET_CATEGORIES))
                raise APIError(
                    message=f"Field 'category' is required and must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["category"] = category

        # 2. Name validation
        if "name" in data or not is_update:
            name = data.get("name")
            if not isinstance(name, str) or len(name.strip()) < 1:
                raise APIError(
                    message="Field 'name' is required and cannot be empty.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["name"] = name.strip()

        # 3. Monetary amounts (distinct fields: estimated, confirmed, actual, paid)
        for amount_field in ("estimated_amount", "confirmed_amount", "actual_amount", "paid_amount"):
            if amount_field in data:
                cleaned[amount_field] = validate_monetary_amount(amount_field, data.get(amount_field))
            elif not is_update:
                cleaned[amount_field] = 0.00

        # 4. Payment status
        if "payment_status" in data:
            status = data.get("payment_status")
            if not isinstance(status, str) or status not in ALLOWED_PAYMENT_STATUSES:
                allowed_str = ", ".join(sorted(ALLOWED_PAYMENT_STATUSES))
                raise APIError(
                    message=f"Field 'payment_status' must be one of: {allowed_str}.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["payment_status"] = status
        elif not is_update:
            cleaned["payment_status"] = "unpaid"

        # 5. Due date
        if "due_date" in data:
            cleaned["due_date"] = parse_due_date(data.get("due_date"))

        # 6. Notes
        if "notes" in data:
            notes = data.get("notes")
            if notes is not None and not isinstance(notes, str):
                raise APIError(
                    message="Field 'notes' must be a string or null.",
                    status_code=400,
                    code="VALIDATION_ERROR",
                )
            cleaned["notes"] = notes

        return cleaned

    # =========================================================================
    # Budget Items CRUD
    # =========================================================================

    def create_budget_item(self, event_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a budget item strictly bound to event_id."""
        validated_data = self.validate_budget_item_data(data, is_update=False)
        # Server-side association: ignore any client-supplied event_id or id
        validated_data["event_id"] = event_id

        try:
            res = self.client.table("budget_items").insert(validated_data).execute()
            if not res.data or len(res.data) == 0:
                raise APIError(
                    message="Failed to insert budget item into database.",
                    status_code=500,
                    code="DATABASE_ERROR",
                )
            return res.data[0]

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "create_budget_item")

    def list_budget_items(
        self,
        event_id: str,
        category: Optional[str] = None,
        payment_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Lists budget items for an event with optional category or status filters."""
        try:
            query = self.client.table("budget_items").select("*").eq("event_id", event_id)

            if category:
                if category not in ALLOWED_BUDGET_CATEGORIES:
                    raise APIError(
                        message=f"Invalid category filter '{category}'.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                query = query.eq("category", category)

            if payment_status:
                if payment_status not in ALLOWED_PAYMENT_STATUSES:
                    raise APIError(
                        message=f"Invalid payment_status filter '{payment_status}'.",
                        status_code=400,
                        code="VALIDATION_ERROR",
                    )
                query = query.eq("payment_status", payment_status)

            query = query.order("created_at", desc=False).range(offset, offset + limit - 1)
            res = query.execute()
            return res.data or []

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "list_budget_items")

    def get_budget_item(self, event_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single budget item, enforcing item-to-event association."""
        try:
            res = (
                self.client.table("budget_items")
                .select("*")
                .eq("id", item_id)
                .eq("event_id", event_id)
                .execute()
            )
            if res.data and len(res.data) > 0:
                return res.data[0]
            return None

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_budget_item")

    def update_budget_item(
        self,
        event_id: str,
        item_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Updates a budget item, enforcing that it belongs to event_id."""
        existing = self.get_budget_item(event_id, item_id)
        if not existing:
            raise APIError(
                message=f"Budget item with id '{item_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        validated_updates = self.validate_budget_item_data(data, is_update=True)
        if not validated_updates:
            return existing

        try:
            res = (
                self.client.table("budget_items")
                .update(validated_updates)
                .eq("id", item_id)
                .eq("event_id", event_id)
                .execute()
            )
            if not res.data or len(res.data) == 0:
                raise APIError(
                    message=f"Budget item with id '{item_id}' could not be updated.",
                    status_code=404,
                    code="NOT_FOUND",
                )
            return res.data[0]

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "update_budget_item")

    def delete_budget_item(self, event_id: str, item_id: str) -> bool:
        """Deletes a budget item, enforcing that it belongs to event_id."""
        existing = self.get_budget_item(event_id, item_id)
        if not existing:
            raise APIError(
                message=f"Budget item with id '{item_id}' not found for event '{event_id}'.",
                status_code=404,
                code="NOT_FOUND",
            )

        try:
            res = (
                self.client.table("budget_items")
                .delete()
                .eq("id", item_id)
                .eq("event_id", event_id)
                .execute()
            )
            return bool(res.data and len(res.data) > 0)

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "delete_budget_item")

    # =========================================================================
    # Budget Aggregation & Summary View
    # =========================================================================

    def get_budget_summary(self, event_id: str, event_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Retrieves aggregated budget summary for an event.

        Queries the event_budget_summaries view when available.
        Maintains distinct formulas:
          - total_estimated: sum(estimated_amount)
          - total_confirmed: sum(confirmed_amount)
          - total_actual: sum(actual_amount)
          - total_paid: sum(paid_amount)
          - remaining_budget: target_budget - total_actual
        """
        try:
            # 1. Attempt reading from PostgreSQL event_budget_summaries view
            view_res = (
                self.client.table("event_budget_summaries")
                .select("*")
                .eq("event_id", event_id)
                .execute()
            )
            if view_res.data and len(view_res.data) > 0:
                row = view_res.data[0]
                return {
                    "event_id": row["event_id"],
                    "owner_id": row.get("owner_id"),
                    "target_budget": row.get("target_budget"),
                    "currency": row.get("currency", "USD"),
                    "total_estimated": float(row.get("total_estimated", 0.00)),
                    "total_confirmed": float(row.get("total_confirmed", 0.00)),
                    "total_actual": float(row.get("total_actual", 0.00)),
                    "total_paid": float(row.get("total_paid", 0.00)),
                    "remaining_budget": float(row.get("remaining_budget", 0.00)),
                    "category_breakdowns": row.get("category_breakdowns", {}),
                }

            # 2. Resilient fallback calculation: compute directly from events + budget_items
            event = event_record
            if not event:
                ev_res = self.client.table("events").select("id, owner_id, target_budget, currency").eq("id", event_id).execute()
                if not ev_res.data or len(ev_res.data) == 0:
                    raise APIError(
                        message=f"Event with id '{event_id}' not found.",
                        status_code=404,
                        code="NOT_FOUND",
                    )
                event = ev_res.data[0]

            items_res = self.client.table("budget_items").select("*").eq("event_id", event_id).execute()
            items = items_res.data or []

            total_estimated = 0.00
            total_confirmed = 0.00
            total_actual = 0.00
            total_paid = 0.00
            category_breakdowns: Dict[str, Dict[str, float]] = {}

            for item in items:
                cat = item.get("category", "other")
                est = float(item.get("estimated_amount", 0.00) or 0.00)
                conf = float(item.get("confirmed_amount", 0.00) or 0.00)
                act = float(item.get("actual_amount", 0.00) or 0.00)
                paid = float(item.get("paid_amount", 0.00) or 0.00)

                total_estimated += est
                total_confirmed += conf
                total_actual += act
                total_paid += paid

                if cat not in category_breakdowns:
                    category_breakdowns[cat] = {
                        "estimated": 0.00,
                        "confirmed": 0.00,
                        "actual": 0.00,
                        "paid": 0.00,
                    }
                category_breakdowns[cat]["estimated"] = round(category_breakdowns[cat]["estimated"] + est, 2)
                category_breakdowns[cat]["confirmed"] = round(category_breakdowns[cat]["confirmed"] + conf, 2)
                category_breakdowns[cat]["actual"] = round(category_breakdowns[cat]["actual"] + act, 2)
                category_breakdowns[cat]["paid"] = round(category_breakdowns[cat]["paid"] + paid, 2)

            target_budget = event.get("target_budget")
            target_budget_val = float(target_budget) if target_budget is not None else 0.00
            remaining_budget = round(target_budget_val - total_actual, 2)

            return {
                "event_id": event_id,
                "owner_id": event.get("owner_id"),
                "target_budget": target_budget,
                "currency": event.get("currency", "USD"),
                "total_estimated": round(total_estimated, 2),
                "total_confirmed": round(total_confirmed, 2),
                "total_actual": round(total_actual, 2),
                "total_paid": round(total_paid, 2),
                "remaining_budget": remaining_budget,
                "category_breakdowns": category_breakdowns,
            }

        except APIError:
            raise
        except Exception as e:
            self._handle_db_error(e, "get_budget_summary")

    # =========================================================================
    # Error Mapping
    # =========================================================================

    def _handle_db_error(self, e: Exception, operation: str) -> None:
        """Translates Supabase/Postgrest errors into standardized APIErrors."""
        error_str = str(e)

        if "check constraint" in error_str.lower() or "23514" in error_str:
            raise APIError(
                message="Data violates budget validation constraints.",
                status_code=400,
                code="VALIDATION_ERROR",
            )
        if "foreign key" in error_str.lower() or "23503" in error_str:
            raise APIError(
                message="Referenced event does not exist.",
                status_code=400,
                code="FOREIGN_KEY_ERROR",
            )
        if "not configured" in error_str.lower() or "connection" in error_str.lower():
            raise APIError(
                message="Database service is temporarily unavailable.",
                status_code=503,
                code="SERVICE_UNAVAILABLE",
            )

        raise APIError(
            message=f"Database operation failed during {operation}.",
            status_code=500,
            code="DATABASE_ERROR",
        )
