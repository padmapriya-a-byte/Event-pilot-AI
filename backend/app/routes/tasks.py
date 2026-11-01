"""EventPilot AI - Task Management API Routes.

Implements owner-authorized REST endpoints for event tasks:
  - GET    /api/events/<event_id>/tasks
  - POST   /api/events/<event_id>/tasks
  - GET    /api/events/<event_id>/tasks/<task_id>
  - PATCH  /api/events/<event_id>/tasks/<task_id>
  - DELETE /api/events/<event_id>/tasks/<task_id>
"""

import uuid
from flask import Blueprint, request, jsonify, current_app

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..services.task_service import TaskService

tasks_bp = Blueprint("tasks", __name__, url_prefix="/api/events/<event_id>/tasks")


def get_task_service() -> TaskService:
    """Returns configured or default TaskService."""
    configured = current_app.config.get("TASK_SERVICE")
    if configured is not None:
        return configured
    return TaskService()


def validate_task_uuid(task_id: str) -> str:
    """Validates that task_id is a syntactically valid UUID string."""
    try:
        return str(uuid.UUID(str(task_id)))
    except (ValueError, TypeError):
        raise APIError(
            message=f"Invalid 'task_id' format: '{task_id}'. Must be a valid UUID.",
            status_code=400,
            code="BAD_REQUEST",
        )


@tasks_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def list_tasks(event_id: str):
    """Lists tasks for an event with optional status/priority filtering."""
    status = request.args.get("status")
    priority = request.args.get("priority")

    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 200)
    except ValueError:
        limit = 100

    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        offset = 0

    service = get_task_service()
    tasks = service.list_tasks(
        event_id=event_id,
        status=status,
        priority=priority,
        limit=limit,
        offset=offset,
    )

    return jsonify({
        "success": True,
        "data": tasks,
        "count": len(tasks),
        "limit": limit,
        "offset": offset,
    }), 200


@tasks_bp.route("", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def create_task(event_id: str):
    """Creates a new task bound to the event."""
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    service = get_task_service()
    created = service.create_task(event_id, data)

    return jsonify({
        "success": True,
        "data": created,
    }), 201


@tasks_bp.route("/<task_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_task(event_id: str, task_id: str):
    """Retrieves a single task belonging to the event."""
    norm_id = validate_task_uuid(task_id)
    service = get_task_service()
    task = service.get_task(event_id, norm_id)
    if not task:
        raise APIError(
            message=f"Task with id '{norm_id}' not found for event '{event_id}'.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": task,
    }), 200


@tasks_bp.route("/<task_id>", methods=["PATCH"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def update_task(event_id: str, task_id: str):
    """Updates a task belonging to the event."""
    norm_id = validate_task_uuid(task_id)
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    service = get_task_service()
    updated = service.update_task(event_id, norm_id, data)

    return jsonify({
        "success": True,
        "data": updated,
    }), 200


@tasks_bp.route("/<task_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_task(event_id: str, task_id: str):
    """Deletes a task belonging to the event."""
    norm_id = validate_task_uuid(task_id)
    service = get_task_service()
    deleted = service.delete_task(event_id, norm_id)
    if not deleted:
        raise APIError(
            message=f"Task with id '{norm_id}' not found for event '{event_id}'.",
            status_code=404,
            code="NOT_FOUND",
        )

    return jsonify({
        "success": True,
        "data": {"id": norm_id, "deleted": True},
    }), 200
