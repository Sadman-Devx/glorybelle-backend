"""
GLORYBELLE — Local Development Settings.

Usage: DJANGO_SETTINGS_MODULE=config.settings.local
"""
from .base import *  # noqa: F401, F403

# =============================================================================
# Debug
# =============================================================================
DEBUG = True

# =============================================================================
# Use local file storage instead of Cloudinary in development
# =============================================================================
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# =============================================================================
# Django Debug Toolbar
# =============================================================================
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
INTERNAL_IPS = ["127.0.0.1"]

# =============================================================================
# Email — console backend for local development
# =============================================================================
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# =============================================================================
# Database — PostgreSQL only (DATABASES is defined in base.py from DATABASE_URL).
# There is intentionally NO SQLite fallback: dev, test and prod all run on the
# same engine. Start the database with:  docker compose up -d db redis
# =============================================================================


# =============================================================================
# Cache — LocMemCache for local dev (no Redis needed for the Django process)
# Celery still uses REDIS_URL as its broker, so keep Redis running if you run
# workers:  docker compose up -d db redis
# =============================================================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# =============================================================================
# Logging — verbose in development
# =============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.db.backends": {
            "level": "WARNING",
            "handlers": ["console"],
        },
        "apps": {
            "level": "DEBUG",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

# =============================================================================
# CORS — Allow Next.js frontend (localhost:3000) in development
# =============================================================================
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True
