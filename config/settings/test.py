"""
GLORYBELLE — Test Settings.

Usage: DJANGO_SETTINGS_MODULE=config.settings.test
Overrides local.py with SQLite + in-memory cache for test speed
and no external dependency requirements (no Redis, no Postgres).
"""
from .local import *  # noqa: F401, F403

# =============================================================================
# Database — SQLite for tests (no Postgres required)
# =============================================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# =============================================================================
# Cache — local memory (no Redis required)
# =============================================================================
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# =============================================================================
# Session — DB-backed for tests (no Redis required)
# =============================================================================
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# =============================================================================
# Celery — always eager in tests (synchronous execution)
# =============================================================================
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# =============================================================================
# Password hashing — fast hasher for tests
# =============================================================================
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# =============================================================================
# Stripe — test mode placeholders
# =============================================================================
STRIPE_SECRET_KEY = "sk_test_placeholder"
STRIPE_WEBHOOK_SECRET = "whsec_placeholder"
