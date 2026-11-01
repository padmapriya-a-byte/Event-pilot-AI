"""EventPilot AI - Event & Preferences API Routes.

Implements RESTful endpoints for event lifecycle management:
  - POST   /api/events
  - GET    /api/events
  - GET    /api/events/<event_id>
  - PATCH  /api/events/<event_id>
  - DELETE /api/events/<event_id>
  - GET    /api/events/<event_id>/preferences
  - PUT    /api/events/<event_id>/preferences
  - PATCH  /api/events/<event_id>/preferences
"""

from typing import Any
from flask import Blueprint, request, jsonify, g, current_app

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..services.event_service import EventService

events_bp = Blueprint("events", __name__, url_prefix="/api/events")


def get_event_service() -> EventService:
    """Returns the configured or default EventService instance."""
    configured_service = current_app.config.get("EVENT_SERVICE")
    if configured_service is not None:
        return configured_service
    return EventService()


# =============================================================================
# Event Endpoints
# =============================================================================

@events_bp.route("", methods=["POST"], strict_slashes=False)
@require_auth
def create_event():
    """Creates a new event under the authenticated user's ownership.

    Client-supplied owner IDs are ignored; owner_id is set to verified g.user_id.
    """
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

    service = get_event_service()
    created_event = service.create_event(owner_id=g.user_id, data=data)

    return jsonify({
        "success": True,
        "data": created_event,
    }), 201


@events_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
def list_events():
    """Lists events belonging to the authenticated user.

    Supports optional query filters: status, include_archived, limit, offset.
    """
    status = request.args.get("status")
    include_archived_param = request.args.get("include_archived", "false").lower()
    include_archived = include_archived_param in ("true", "1", "yes")

    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except ValueError:
        limit = 50

    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        offset = 0

    service = get_event_service()
    events = service.list_events(
        owner_id=g.user_id,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )

    return jsonify({
        "success": True,
        "data": events,
        "count": len(events),
        "limit": limit,
        "offset": offset,
    }), 200


@events_bp.route("/<event_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_event(event_id: str):
    """Retrieves a single event owned by the authenticated user."""
    service = get_event_service()
    event = service.get_event(event_id=event_id, owner_id=g.user_id)

    if not event:
        raise APIError(
            message=f"Event with id '{event_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": event,
    }), 200


@events_bp.route("/<event_id>", methods=["PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_event(event_id: str):
    """Updates fields of an event owned by the authenticated user."""
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

    service = get_event_service()
    updated_event = service.update_event(
        event_id=event_id,
        owner_id=g.user_id,
        data=data,
    )

    return jsonify({
        "success": True,
        "data": updated_event,
    }), 200


@events_bp.route("/<event_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_event(event_id: str):
    """Deletes an event owned by the authenticated user."""
    service = get_event_service()
    deleted = service.delete_event(event_id=event_id, owner_id=g.user_id)

    if not deleted:
        raise APIError(
            message=f"Event with id '{event_id}' not found or already deleted.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": {
            "id": event_id,
            "deleted": True,
        },
    }), 200


# =============================================================================
# Event Preferences Endpoints
# =============================================================================

@events_bp.route("/<event_id>/preferences", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_preferences(event_id: str):
    """Retrieves preferences for an event owned by the authenticated user."""
    service = get_event_service()
    preferences = service.get_preferences(event_id=event_id)

    return jsonify({
        "success": True,
        "data": preferences,
    }), 200


@events_bp.route("/<event_id>/preferences", methods=["PUT", "PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_preferences(event_id: str):
    """Updates or upserts preferences for an event owned by the authenticated user."""
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

    service = get_event_service()
    updated_preferences = service.update_preferences(
        event_id=event_id,
        data=data,
    )

    return jsonify({
        "success": True,
        "data": updated_preferences,
    }), 200
