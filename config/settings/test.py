"""
GLORYBELLE — Test Settings.

Usage: DJANGO_SETTINGS_MODULE=config.settings.test

Tests run on PostgreSQL (same engine as production) so that behaviour such as
select_for_update() row locking is actually exercised. The database comes from
DATABASE_URL; pytest-django creates a separate `test_<name>` database, so your
dev data is never touched. The DB user must be allowed to CREATE DATABASE
(the docker-compose Postgres user is).

Start the database first:  docker compose up -d db
Redis is NOT required: cache is in-memory and Celery runs eagerly.
"""
from .local import *  # noqa: F401, F403

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
