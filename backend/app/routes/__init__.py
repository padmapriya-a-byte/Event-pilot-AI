"""Route blueprints registration for EventPilot AI."""

from .health import health_bp
from .events import events_bp
from .budget import budget_bp
from .ai import ai_bp
from .venues import venues_bp, agenda_bp
from .tasks import tasks_bp
from .exports import exports_bp

__all__ = [
    "health_bp",
    "events_bp",
    "budget_bp",
    "ai_bp",
    "venues_bp",
    "agenda_bp",
    "tasks_bp",
    "exports_bp",
]
