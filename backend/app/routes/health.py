"""Health check and foundational status routes."""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
from ..config import Config

health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Returns application health, environment status, and integration flags."""
    return jsonify({
        "success": True,
        "data": {
            "status": "healthy",
            "service": "EventPilot-AI Backend",
            "environment": Config.ENV,
            "version": "1.0.0",
            "integrations": {
                "gemini_ai": {
                    "configured": Config.is_gemini_configured(),
                    "model": Config.GEMINI_MODEL,
                },
                "supabase": {
                    "configured": Config.is_supabase_configured(),
                    "url_provided": bool(Config.SUPABASE_URL),
                },
            },
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


@health_bp.route("/status", methods=["GET"])
def system_status():
    """Lightweight ping endpoint for load balancers and deployment probes."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200
