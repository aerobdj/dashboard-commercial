# app/controllers/__init__.py
# Bisa dikosongkan. Atau mengimpor blueprint untuk kemudahan ekspor:

from app.controllers.auth_controller import auth_bp
from app.controllers.dashboard_controller import dashboard_bp

__all__ = ['auth_bp', 'dashboard_bp']