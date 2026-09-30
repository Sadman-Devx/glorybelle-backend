# Import celery app for autodiscovery when Django starts.
from .celery import app as celery_app

__all__ = ["celery_app"]
