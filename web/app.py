"""WarPie Web Control Panel - Flask Application Factory.

Version: 3.0.0
Provides a mobile-optimized web interface for controlling Kismet wardriving
on Raspberry Pi with cyberpunk aesthetic and HTMX for dynamic updates.
"""

from flask import Flask

from web.routes import filters_bp, logs_bp, main_bp, targets_bp


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(filters_bp, url_prefix="/api")
    app.register_blueprint(targets_bp, url_prefix="/api")
    app.register_blueprint(logs_bp, url_prefix="/api")

    return app
