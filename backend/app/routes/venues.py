"""EventPilot AI - Venue & Agenda Session API Routes.

Implements owner-authorized REST endpoints:
  - Venues:
    - GET    /api/events/<event_id>/venues
    - POST   /api/events/<event_id>/venues
    - GET    /api/events/<event_id>/venues/<venue_id>
    - PATCH  /api/events/<event_id>/venues/<venue_id>
    - DELETE /api/events/<event_id>/venues/<venue_id>
  - Agenda Sessions:
    - GET    /api/events/<event_id>/agenda
    - POST   /api/events/<event_id>/agenda
    - GET    /api/events/<event_id>/agenda/<session_id>
    - PATCH  /api/events/<event_id>/agenda/<session_id>
    - DELETE /api/events/<event_id>/agenda/<session_id>
"""

import uuid
from flask import Blueprint, request, jsonify, current_app, g

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..services.venue_service import VenueService

venues_bp = Blueprint("venues", __name__, url_prefix="/api/events/<event_id>/venues")
agenda_bp = Blueprint("agenda", __name__, url_prefix="/api/events/<event_id>/agenda")


def get_venue_service() -> VenueService:
    """Returns configured or default VenueService."""
    configured = current_app.config.get("VENUE_SERVICE")
    if configured is not None:
        return configured
    return VenueService()


def validate_uuid(val: str, field_name: str) -> str:
    """Validates that a string is a valid UUID."""
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, TypeError):
        raise APIError(
            message=f"Invalid '{field_name}' format: '{val}'. Must be a valid UUID.",
            status_code=400,
            code="BAD_REQUEST",
        )


# =============================================================================
# Venues Endpoints
# =============================================================================

@venues_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def list_venues(event_id: str):
    """Lists all venues shortlisted or selected for an event."""
    service = get_venue_service()
    venues = service.list_venues(event_id)
    return jsonify({
        "success": True,
        "data": venues,
        "count": len(venues),
    }), 200


@venues_bp.route("", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def create_venue(event_id: str):
    """Creates a new venue candidate for the event."""
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    user_token = getattr(g, "token", None)
    service = get_venue_service()
    created = service.create_venue(event_id, data, user_token=user_token)
    return jsonify({
        "success": True,
        "data": created,
    }), 201


@venues_bp.route("/<venue_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_venue(event_id: str, venue_id: str):
    """Retrieves a single venue belonging to the event."""
    norm_id = validate_uuid(venue_id, "venue_id")
    service = get_venue_service()
    venue = service.get_venue(event_id, norm_id)
    if not venue:
        raise APIError(f"Venue with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": venue,
    }), 200


@venues_bp.route("/<venue_id>", methods=["PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_venue(event_id: str, venue_id: str):
    """Updates a venue, enforcing at most one selected venue."""
    norm_id = validate_uuid(venue_id, "venue_id")
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    user_token = getattr(g, "token", None)
    service = get_venue_service()
    updated = service.update_venue(event_id, norm_id, data, user_token=user_token)
    return jsonify({
        "success": True,
        "data": updated,
    }), 200


@venues_bp.route("/<venue_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_venue(event_id: str, venue_id: str):
    """Deletes a venue from the event."""
    norm_id = validate_uuid(venue_id, "venue_id")
    service = get_venue_service()
    deleted = service.delete_venue(event_id, norm_id)
    if not deleted:
        raise APIError(f"Venue with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": {"id": norm_id, "deleted": True},
    }), 200


# =============================================================================
# Agenda Sessions Endpoints
# =============================================================================

@agenda_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def list_sessions(event_id: str):
    """Lists agenda sessions for an event ordered chronologically."""
    service = get_venue_service()
    sessions = service.list_sessions(event_id)
    return jsonify({
        "success": True,
        "data": sessions,
        "count": len(sessions),
    }), 200


@agenda_bp.route("", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def create_session(event_id: str):
    """Creates an agenda session, verifying start_time < end_time and venue boundary."""
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    service = get_venue_service()
    created = service.create_session(event_id, data)
    return jsonify({
        "success": True,
        "data": created,
    }), 201


@agenda_bp.route("/<session_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_session(event_id: str, session_id: str):
    """Retrieves an agenda session belonging to the event."""
    norm_id = validate_uuid(session_id, "session_id")
    service = get_venue_service()
    session = service.get_session(event_id, norm_id)
    if not session:
        raise APIError(f"Agenda session with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": session,
    }), 200


@agenda_bp.route("/<session_id>", methods=["PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_session(event_id: str, session_id: str):
    """Updates an agenda session, enforcing boundaries and time ordering."""
    norm_id = validate_uuid(session_id, "session_id")
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    service = get_venue_service()
    updated = service.update_session(event_id, norm_id, data)
    return jsonify({
        "success": True,
        "data": updated,
    }), 200


@agenda_bp.route("/<session_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_session(event_id: str, session_id: str):
    """Deletes an agenda session from the event."""
    norm_id = validate_uuid(session_id, "session_id")
    service = get_venue_service()
    deleted = service.delete_session(event_id, norm_id)
    if not deleted:
        raise APIError(f"Agenda session with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": {"id": norm_id, "deleted": True},
    }), 200
