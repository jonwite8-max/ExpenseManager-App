# app/routes/__init__.py
from .auth import auth_bp
from .dashboard import dashboard_bp
from .orders import orders_bp
from .workers import workers_bp
from .expenses import expenses_bp
from .transport import transport_bp
from .debts import debts_bp
from .tasks import tasks_bp
from .settings import settings_bp
from .reports import reports_bp

__all__ = [
    'auth_bp',
    'dashboard_bp', 
    'orders_bp',
    'workers_bp',
    'expenses_bp',
    'transport_bp',
    'debts_bp',
    'tasks_bp',
    'settings_bp',
    'reports_bp'
]