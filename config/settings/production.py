"""
GLORYBELLE — Production Settings.

Usage: DJANGO_SETTINGS_MODULE=config.settings.production
"""
import sentry_sdk
from decouple import config

from .base import *  # noqa: F401, F403

# =============================================================================
# Debug — NEVER True in production
# =============================================================================
DEBUG = False

# =============================================================================
# Security headers
# =============================================================================
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# =============================================================================
# Sentry — error tracking
# =============================================================================
SENTRY_DSN = config("SENTRY_DSN", default="")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
    )

# =============================================================================
# Logging — structured for production
# =============================================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django.security": {
            "level": "WARNING",
            "handlers": ["console"],
        },
        "apps": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}
