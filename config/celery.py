"""
Celery application for GLORYBELLE.

Handles async tasks: email, invoicing, stock reservation cleanup.
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("glorybelle")

# Read config from Django settings, namespace='CELERY' means all Celery
# config keys must be prefixed with 'CELERY_' in settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in each installed app.
app.autodiscover_tasks()

# Celery Beat schedule — periodic tasks.
app.conf.beat_schedule = {
    "release-expired-reservations": {
        "task": "apps.cart.tasks.release_expired_reservations",
        "schedule": 60.0,  # Every 60 seconds
    },
}
