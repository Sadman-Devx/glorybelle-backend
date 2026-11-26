# Import celery app for autodiscovery when Django starts.
from .celery import app as celery_app

from . import checks  # noqa: F401,E402 — registers `manage.py check --deploy` checks

__all__ = ["celery_app"]
