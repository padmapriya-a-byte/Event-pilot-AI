"""EventPilot AI - Gemini AI Planning & Budget Optimization Routes.

Implements owner-authorized AI endpoints:
  - POST /api/ai/plan-event
  - POST /api/ai/budget-optimize
"""

from typing import Any, Dict
from flask import Blueprint, request, jsonify, g, current_app

from ..utils.auth import require_auth, require_event_owner
from ..utils.errors import APIError
from ..utils.limiter import limiter
from ..services.gemini_service import GeminiService
from ..services.event_service import EventService
from ..services.budget_service import BudgetService

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


def get_gemini_service() -> GeminiService:
    """Returns configured or default GeminiService."""
    configured = current_app.config.get("GEMINI_SERVICE")
    if configured is not None:
        return configured
    return GeminiService()


def get_event_service() -> EventService:
    """Returns configured or default EventService."""
    configured = current_app.config.get("EVENT_SERVICE")
    if configured is not None:
        return configured
    return EventService()


def get_budget_service() -> BudgetService:
    """Returns configured or default BudgetService."""
    configured = current_app.config.get("BUDGET_SERVICE")
    if configured is not None:
        return configured
    return BudgetService()


# =============================================================================
# AI Event Planning Endpoint
# =============================================================================

@ai_bp.route("/plan-event", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_AI_LIMIT", "5 per minute"))
def plan_event():
    """Generates a complete event master plan using Gemini and saves a revision via PostgreSQL RPC.

    Requires authenticated session and verifies event ownership.
    Treats user notes as untrusted context.
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

    event_id = str(data.get("event_id"))
    event = getattr(g, "current_event", None)
    if not event:
        raise APIError(
            message=f"Event with id '{event_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )

    prompt_context = data.get("prompt_context")
    if prompt_context is not None and not isinstance(prompt_context, dict):
        raise APIError(
            message="Field 'prompt_context' must be a JSON object or null.",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    change_summary = data.get("change_summary")
    if change_summary is not None and not isinstance(change_summary, str):
        raise APIError(
            message="Field 'change_summary' must be a string or null.",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    # Extract user notes/description safely
    user_notes = None
    if prompt_context:
        user_notes = prompt_context.get("user_notes") or prompt_context.get("notes")
    if not user_notes and event.get("description"):
        user_notes = event.get("description")

    # Fetch event preferences
    event_service = get_event_service()
    preferences = event_service.get_preferences(event_id)

    # Fetch baseline budget summary
    budget_service = get_budget_service()
    budget_summary = budget_service.get_budget_summary(event_id, event_record=event)

    # Call Gemini planning service
    gemini_service = get_gemini_service()
    plan_content = gemini_service.generate_event_plan(
        event=event,
        preferences=preferences,
        budget_summary=budget_summary,
        user_notes=str(user_notes) if user_notes else None,
    )

    plan_title = plan_content.get("theme") or f"{event.get('title', 'Event')} Master Plan"
    plan_summary = plan_content.get("summary") or "AI-generated event master plan"

    # Persist via PostgreSQL create_and_activate_plan_revision RPC
    user_token = getattr(g, "token", None)
    saved_revision = gemini_service.save_plan_revision(
        event_id=event_id,
        title=plan_title,
        summary=plan_summary,
        content=plan_content,
        prompt_context=prompt_context,
        change_summary=change_summary or "AI plan generation",
        user_token=user_token,
        supabase_service=current_app.config.get("SUPABASE_ADMIN_SERVICE"),
    )

    return jsonify({
        "success": True,
        "data": {
            "plan": saved_revision,
            "generated_content": plan_content,
        },
    }), 201


# =============================================================================
# AI Budget Optimization Endpoint
# =============================================================================

@ai_bp.route("/budget-optimize", methods=["POST"], strict_slashes=False)
@require_auth
@require_event_owner("event_id")
@limiter.limit(lambda: current_app.config.get("RATELIMIT_AI_LIMIT", "5 per minute"))
def budget_optimize():
    """Generates AI budget optimization strategies for an event owned by the caller."""
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

    event_id = str(data.get("event_id"))
    event = getattr(g, "current_event", None)
    if not event:
        raise APIError(
            message=f"Event with id '{event_id}' not found.",
            status_code=404,
            code="NOT_FOUND",
        )

    optimization_goal = data.get("optimization_goal")
    if optimization_goal is not None and not isinstance(optimization_goal, str):
        raise APIError(
            message="Field 'optimization_goal' must be a string or null.",
            status_code=400,
            code="VALIDATION_ERROR",
        )

    # Fetch budget items and summary
    budget_service = get_budget_service()
    budget_items = budget_service.list_budget_items(event_id)
    budget_summary = budget_service.get_budget_summary(event_id, event_record=event)

    # Call Gemini budget optimization
    gemini_service = get_gemini_service()
    optimization_result = gemini_service.optimize_budget(
        event=event,
        budget_items=budget_items,
        budget_summary=budget_summary,
        optimization_goal=optimization_goal,
    )

    return jsonify({
        "success": True,
        "data": optimization_result,
    }), 200
