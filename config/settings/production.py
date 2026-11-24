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
# Keep True behind a real HTTPS proxy. Set SECURE_SSL_REDIRECT=False in .env only
# when running this image locally over plain http (docker compose on localhost).
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
# Container/orchestrator healthchecks hit plain http — never redirect them.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# =============================================================================
# Static files — served by WhiteNoise from inside the container (gunicorn does
# not serve /static/ by itself, so the admin would have no CSS/JS otherwise).
# collectstatic runs at image build time (see Dockerfile).
# =============================================================================
MIDDLEWARE.insert(  # noqa: F405
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,  # noqa: F405
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

# Media — Cloudinary when credentials are set, otherwise local disk (the
# docker-compose `media_files` volume). NOTE: Django 5.1 removed the old
# DEFAULT_FILE_STORAGE setting used in base.py, so STORAGES is required.
_use_cloudinary = bool(config("CLOUDINARY_CLOUD_NAME", default=""))
STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if _use_cloudinary
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

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
