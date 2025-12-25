"""WarPie Web Control Panel - Route Blueprints."""

from web.routes.filters import filters_bp
from web.routes.logs import logs_bp
from web.routes.main import main_bp
from web.routes.targets import targets_bp

__all__ = ["filters_bp", "logs_bp", "main_bp", "targets_bp"]
