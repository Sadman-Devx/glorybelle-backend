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
# Database — PostgreSQL primary, SQLite fallback
# Tries to connect to PostgreSQL (DATABASE_URL from .env via base.py).
# If PostgreSQL is unavailable, falls back to SQLite automatically.
# =============================================================================
try:
    import psycopg2  # noqa: F401

    from django.db import connections  # noqa: F401

    # Test if PostgreSQL is actually reachable
    import dj_database_url

    _db_url = config("DATABASE_URL", default="")  # noqa: F405
    if _db_url:
        _test_conf = dj_database_url.parse(_db_url)
        _conn = psycopg2.connect(
            dbname=_test_conf.get("NAME", ""),
            user=_test_conf.get("USER", ""),
            password=_test_conf.get("PASSWORD", ""),
            host=_test_conf.get("HOST", "localhost"),
            port=_test_conf.get("PORT", "5432"),
            connect_timeout=2,
        )
        _conn.close()
        # PostgreSQL is reachable — use it (already set in base.py)
        print("[DB] Using PostgreSQL")
    else:
        raise Exception("No DATABASE_URL")
except Exception:
    # PostgreSQL unavailable — fall back to SQLite
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }
    print("[DB] PostgreSQL unavailable, using SQLite fallback")


# =============================================================================
# Cache — LocMemCache for local dev without Redis
# If Redis is running (docker compose up), comment this block to use Redis.
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
