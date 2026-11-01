"""EventPilot AI - Budget API Routes.

Implements owner-authorized REST endpoints for budget items and summaries:
  - GET    /api/events/<event_id>/budget/summary
  - GET    /api/events/<event_id>/budget/items
  - POST   /api/events/<event_id>/budget/items
  - GET    /api/events/<event_id>/budget/items/<item_id>
  - PATCH  /api/events/<event_id>/budget/items/<item_id>
  - DELETE /api/events/<event_id>/budget/items/<item_id>
  - GET    /api/events/<event_id>/budget (convenience alias to summary)
"""

import uuid
from flask import Blueprint, request, jsonify, g, current_app

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..services.budget_service import BudgetService

budget_bp = Blueprint("budget", __name__, url_prefix="/api/events/<event_id>/budget")


def get_budget_service() -> BudgetService:
    """Returns the configured or default BudgetService instance."""
    configured_service = current_app.config.get("BUDGET_SERVICE")
    if configured_service is not None:
        return configured_service
    return BudgetService()


def validate_item_uuid(item_id: str) -> str:
    """Validates that item_id is a syntactically valid UUID string."""
    try:
        return str(uuid.UUID(str(item_id)))
    except (ValueError, TypeError):
        raise APIError(
            message=f"Invalid 'item_id' format: '{item_id}'. Must be a valid UUID.",
            status_code=400,
            code="BAD_REQUEST",
        )


# =============================================================================
# Budget Summary Endpoint
# =============================================================================

@budget_bp.route("/summary", methods=["GET"], strict_slashes=False)
@budget_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_summary(event_id: str):
    """Retrieves aggregated budget summary for an event owned by the caller.

    Maintains distinct formulas for total_estimated, total_confirmed, total_actual,
    total_paid, and remaining_budget (target_budget - total_actual).
    """
    service = get_budget_service()
    summary = service.get_budget_summary(event_id=event_id, event_record=getattr(g, "current_event", None))

    return jsonify({
        "success": True,
        "data": summary,
    }), 200


# =============================================================================
# Budget Items Endpoints
# =============================================================================

@budget_bp.route("/items", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def list_items(event_id: str):
    """Lists budget items belonging to the specified event.

    Supports optional query filters: category, payment_status, limit, offset.
    """
    category = request.args.get("category")
    payment_status = request.args.get("payment_status")

    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 200)
    except ValueError:
        limit = 100

    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        offset = 0

    service = get_budget_service()
    items = service.list_budget_items(
        event_id=event_id,
        category=category,
        payment_status=payment_status,
        limit=limit,
        offset=offset,
    )

    return jsonify({
        "success": True,
        "data": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }), 200


@budget_bp.route("/items", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def create_item(event_id: str):
    """Creates a budget item strictly bound to the target event."""
    if not request.is_json:
        raise APIError(
            message="Request body must be valid JSON.",
            status_code=400,
            code="BAD_REQUEST",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(
            message="JSON payload must be an object.",
            status_code=400,
            code="BAD_REQUEST",
        )

    service = get_budget_service()
    created_item = service.create_budget_item(event_id=event_id, data=data)

    return jsonify({
        "success": True,
        "data": created_item,
    }), 201


@budget_bp.route("/items/<item_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_item(event_id: str, item_id: str):
    """Retrieves a single budget item, enforcing event-item relationship."""
    normalized_item_id = validate_item_uuid(item_id)
    service = get_budget_service()
    item = service.get_budget_item(event_id=event_id, item_id=normalized_item_id)

    if not item:
        raise APIError(
            message=f"Budget item with id '{normalized_item_id}' not found for event '{event_id}'.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": item,
    }), 200


@budget_bp.route("/items/<item_id>", methods=["PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_item(event_id: str, item_id: str):
    """Updates fields of a budget item, enforcing event-item relationship."""
    normalized_item_id = validate_item_uuid(item_id)

    if not request.is_json:
        raise APIError(
            message="Request body must be valid JSON.",
            status_code=400,
            code="BAD_REQUEST",
        )

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(
            message="JSON payload must be an object.",
            status_code=400,
            code="BAD_REQUEST",
        )

    service = get_budget_service()
    updated_item = service.update_budget_item(
        event_id=event_id,
        item_id=normalized_item_id,
        data=data,
    )

    return jsonify({
        "success": True,
        "data": updated_item,
    }), 200


@budget_bp.route("/items/<item_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_item(event_id: str, item_id: str):
    """Deletes a budget item, enforcing event-item relationship."""
    normalized_item_id = validate_item_uuid(item_id)

    service = get_budget_service()
    deleted = service.delete_budget_item(event_id=event_id, item_id=normalized_item_id)

    if not deleted:
        raise APIError(
            message=f"Budget item with id '{normalized_item_id}' not found for event '{event_id}'.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": {
            "id": normalized_item_id,
            "deleted": True,
        },
    }), 200
