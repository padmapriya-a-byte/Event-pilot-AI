"""EventPilot AI - Flask Application Factory.

Initializes Flask app with CORS, blueprints, error handlers, and configuration.
"""

from typing import Type, Optional
from flask import Flask
from flask_cors import CORS
from .config import Config
from .utils.errors import register_error_handlers
from .utils.limiter import limiter
from .routes.health import health_bp
from .routes.events import events_bp
from .routes.budget import budget_bp
from .routes.ai import ai_bp
from .routes.venues import venues_bp, agenda_bp
from .routes.tasks import tasks_bp
from .routes.exports import exports_bp


def create_app(config_class: Optional[Type[Config]] = None) -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__)

    # Apply configuration
    cfg = config_class or Config
    app.config.from_object(cfg)

    # Validate production security invariants
    cfg.validate_production_invariants()

    # Initialize CORS for allowed frontend origins
    CORS(
        app,
        resources={r"/api/*": {"origins": cfg.CORS_ORIGINS}},
        supports_credentials=True,
    )

    # Register error handlers
    register_error_handlers(app)

    # Initialize application rate limiter
    limiter.init_app(app)

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(budget_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(venues_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(exports_bp)

    @app.route("/")
    def index():
        return {
            "name": "EventPilot AI Backend API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return app
