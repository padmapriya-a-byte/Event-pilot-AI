"""Standardized error responses and exceptions for EventPilot AI API."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from flask import Flask, jsonify, Response


class APIError(Exception):
    """Custom API exception with HTTP status code and structured payload."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: str = "BAD_REQUEST",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def handle_api_error(error: APIError) -> Response:
    """Format and return an APIError response."""
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response


def register_error_handlers(app: Flask) -> None:
    """Register HTTP error handlers on the Flask app."""

    @app.errorhandler(APIError)
    def on_api_error(error: APIError):
        return handle_api_error(error)

    @app.errorhandler(400)
    def on_bad_request(e):
        return jsonify({
            "success": False,
            "error": {"code": "BAD_REQUEST", "message": "The request was invalid."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 400

    @app.errorhandler(401)
    def on_unauthorized(e):
        return jsonify({
            "success": False,
            "error": {"code": "UNAUTHORIZED", "message": "Authentication required."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 401

    @app.errorhandler(403)
    def on_forbidden(e):
        return jsonify({
            "success": False,
            "error": {"code": "FORBIDDEN", "message": "Access forbidden."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 403

    @app.errorhandler(404)
    def on_not_found(e):
        return jsonify({
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "The requested resource was not found."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 404

    @app.errorhandler(405)
    def on_method_not_allowed(e):
        return jsonify({
            "success": False,
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "HTTP method not allowed on this endpoint."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 405

    @app.errorhandler(429)
    def on_rate_limit_exceeded(e):
        return jsonify({
            "success": False,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": getattr(e, "description", "Rate limit exceeded. Please retry in a few moments."),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 429

    @app.errorhandler(500)
    def on_internal_error(e):
        return jsonify({
            "success": False,
            "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }), 500
