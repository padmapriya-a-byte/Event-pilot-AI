"""EventPilot AI - Plan Exports API Routes.

Implements owner-authorized REST endpoints for generating, listing, and downloading deliverables:
  - POST   /api/events/<event_id>/exports
  - GET    /api/events/<event_id>/exports
  - GET    /api/events/<event_id>/exports/<export_id>
  - GET    /api/events/<event_id>/exports/<export_id>/download
  - DELETE /api/events/<event_id>/exports/<export_id>
"""

import uuid
from flask import Blueprint, request, jsonify, g, current_app, Response

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..config import Config
from ..services.export_service import ExportService

exports_bp = Blueprint("exports", __name__, url_prefix="/api/events/<event_id>/exports")


def get_export_service() -> ExportService:
    """Returns configured or default ExportService."""
    configured = current_app.config.get("EXPORT_SERVICE")
    if configured is not None:
        return configured
    admin_service = current_app.config.get("SUPABASE_ADMIN_SERVICE")
    bucket_name = current_app.config.get("STORAGE_EXPORTS_BUCKET", Config.STORAGE_EXPORTS_BUCKET)
    return ExportService(admin_service=admin_service, bucket_name=bucket_name)


def validate_export_uuid(export_id: str) -> str:
    """Validates that export_id is a syntactically valid UUID string."""
    try:
        return str(uuid.UUID(str(export_id)))
    except (ValueError, TypeError):
        raise APIError(
            message=f"Invalid 'export_id' format: '{export_id}'. Must be a valid UUID.",
            status_code=400,
            code="BAD_REQUEST",
        )


@exports_bp.route("", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def generate_export(event_id: str):
    """Triggers generation of an event deliverable (PDF, ICS, CSV, JSON)."""
    if not request.is_json:
        raise APIError("Request body must be valid JSON.", status_code=400, code="BAD_REQUEST")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError("JSON payload must be an object.", status_code=400, code="BAD_REQUEST")

    export_type = data.get("export_type")
    if not export_type or not isinstance(export_type, str):
        raise APIError("Field 'export_type' is required and must be a string.", status_code=400, code="VALIDATION_ERROR")

    plan_id = data.get("plan_id")
    user_id = getattr(g, "user_id", None)

    service = get_export_service()
    export_record = service.generate_export(
        event_id=event_id,
        export_type=export_type,
        user_id=user_id,
        plan_id=plan_id,
    )

    return jsonify({
        "success": True,
        "data": export_record,
    }), 201


@exports_bp.route("", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def list_exports(event_id: str):
    """Lists metadata for all exports created for the event."""
    service = get_export_service()
    exports = service.list_exports(event_id)
    return jsonify({
        "success": True,
        "data": exports,
        "count": len(exports),
    }), 200


@exports_bp.route("/<export_id>", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def get_export_metadata(event_id: str, export_id: str):
    """Retrieves metadata of a specific export deliverable."""
    norm_id = validate_export_uuid(export_id)
    service = get_export_service()
    export_record = service.get_export_metadata(event_id, norm_id)
    if not export_record:
        raise APIError(f"Export with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": export_record,
    }), 200


@exports_bp.route("/<export_id>/download", methods=["GET"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def download_export_file(event_id: str, export_id: str):
    """Streams the private deliverable file to the authorized event owner."""
    norm_id = validate_export_uuid(export_id)
    service = get_export_service()
    file_bytes, mime_type, filename = service.download_export(event_id, norm_id)

    response = Response(file_bytes, mimetype=mime_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Content-Length"] = str(len(file_bytes))
    return response


@exports_bp.route("/<export_id>", methods=["DELETE"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
def delete_export(event_id: str, export_id: str):
    """Deletes an export record and its associated private storage artifact."""
    norm_id = validate_export_uuid(export_id)
    service = get_export_service()
    deleted = service.delete_export(event_id, norm_id)
    if not deleted:
        raise APIError(f"Export with id '{norm_id}' not found for event '{event_id}'.", status_code=404, code="NOT_FOUND")

    return jsonify({
        "success": True,
        "data": {"id": norm_id, "deleted": True},
    }), 200
