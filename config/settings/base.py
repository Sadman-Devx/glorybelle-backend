"""
GLORYBELLE — Base Settings (shared across all environments).

Never import this file directly. Use local.py or production.py instead.

P1 fix #12: adds django-unfold + token_blacklist apps, FRONTEND_URL + FATTURA24_TEMPLATE_ID
config. UNFOLD settings provide branded admin per roadmap Day 9.
"""
import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from decimal import Decimal

# =============================================================================
# Paths
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# Security
# =============================================================================
SECRET_KEY = config("SECRET_KEY")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
NUM_PROXIES = config("NUM_PROXIES", default=0, cast=int)
if NUM_PROXIES < 0:
    raise ValueError("NUM_PROXIES must be a non-negative integer.")

# Frontend URL — used for password-reset email link (P1 fix #10)
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# =============================================================================
# Application definition
# =============================================================================
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    # P1 fix #10 — token_blacklist needed for logout (blacklist refresh tokens)
    "rest_framework_simplejwt.token_blacklist",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_filters",
    "corsheaders",
    "simple_history",
    "drf_spectacular",
    "cloudinary_storage",
    "cloudinary",
]

LOCAL_APPS = [
    "admin_api.apps.AdminApiConfig",
    "apps.accounts",
    "apps.catalog",
    "apps.cart",
    "apps.enquiries.apps.EnquiriesConfig",
    "apps.site_content.apps.SiteContentConfig",
    "apps.orders",
    "apps.payments",
    "apps.invoicing",
    "apps.wishlist",
    "apps.reviews",
    "apps.newsletter",
]

# Unfold must replace the admin site before Django's admin autodiscovery runs.
INSTALLED_APPS = ["unfold"] + DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# Middleware
# =============================================================================
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "admin_api.middleware.AdminSessionPolicyMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "admin_api.middleware.AdminSecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# =============================================================================
# Database — PostgreSQL via dj-database-url
# =============================================================================
import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# =============================================================================
# Cache — Redis
# =============================================================================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "glorybelle",
        "TIMEOUT": 300,  # 5 minutes default cache TTL
    }
}

# =============================================================================
# Session — Redis-backed
# =============================================================================
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# =============================================================================
# Password validation
# =============================================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =============================================================================
# Internationalization — Italian market
# =============================================================================
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("it", "Italiano"),
    ("en", "English"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Rome"
USE_I18N = True
USE_TZ = True

# =============================================================================
# Static & Media files
# =============================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cloudinary storage — prepared but uses local storage if CLOUDINARY_URL is
# a placeholder. In production, set CLOUDINARY_URL properly.
DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": config("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY": config("CLOUDINARY_API_KEY", default=""),
    "API_SECRET": config("CLOUDINARY_API_SECRET", default=""),
}

# Admin uploads use an isolated S3-compatible bucket; legacy uploads continue
# to use the configured default storage above.
ADMIN_MEDIA_S3_BUCKET = config("ADMIN_MEDIA_S3_BUCKET", default="")
ADMIN_MEDIA_S3_REGION = config("ADMIN_MEDIA_S3_REGION", default="eu-central-1")
ADMIN_MEDIA_S3_ENDPOINT_URL = config("ADMIN_MEDIA_S3_ENDPOINT_URL", default="")
ADMIN_MEDIA_S3_ACCESS_KEY_ID = config("ADMIN_MEDIA_S3_ACCESS_KEY_ID", default="")
ADMIN_MEDIA_S3_SECRET_ACCESS_KEY = config(
    "ADMIN_MEDIA_S3_SECRET_ACCESS_KEY", default=""
)
ADMIN_MEDIA_PUBLIC_BASE_URL = config("ADMIN_MEDIA_PUBLIC_BASE_URL", default="")
ADMIN_MEDIA_PRESIGN_TTL = config("ADMIN_MEDIA_PRESIGN_TTL", default=300, cast=int)

# =============================================================================
# Default primary key field type
# =============================================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# Django REST Framework
# =============================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 8,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "core.throttling.AnonRateThrottle",
        "core.throttling.UserRateThrottle",
    ],
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "1000/hour",
        "user": "1000/hour",
        "admin_login": "5/minute",
        "enquiry_create": "5/hour",
        "order_lookup": "20/min",
        "login": "10/min",
    },
}

# =============================================================================
# Simple JWT
# =============================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # P1 fix #10 — needed for logout endpoint
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

ADMIN_SESSION_IDLE_TIMEOUT_SECONDS = config(
    "ADMIN_SESSION_IDLE_TIMEOUT_SECONDS", default=1800, cast=int
)
ADMIN_LOGIN_FAILURE_LIMIT = config("ADMIN_LOGIN_FAILURE_LIMIT", default=3, cast=int)
ADMIN_LOGIN_LOCKOUT_SECONDS = config(
    "ADMIN_LOGIN_LOCKOUT_SECONDS", default=900, cast=int
)
ADMIN_MFA_CHALLENGE_TTL_SECONDS = config(
    "ADMIN_MFA_CHALLENGE_TTL_SECONDS", default=600, cast=int
)
ADMIN_MFA_RECOVERY_CODE_COUNT = config(
    "ADMIN_MFA_RECOVERY_CODE_COUNT", default=10, cast=int
)
if (
    ADMIN_SESSION_IDLE_TIMEOUT_SECONDS < 60
    or ADMIN_LOGIN_FAILURE_LIMIT < 1
    or ADMIN_LOGIN_LOCKOUT_SECONDS < 60
    or ADMIN_MFA_CHALLENGE_TTL_SECONDS < 60
    or ADMIN_MFA_RECOVERY_CODE_COUNT < 1
):
    raise ValueError("Admin security timeout and count settings are invalid.")

# =============================================================================
# drf-spectacular — OpenAPI schema
# =============================================================================
SPECTACULAR_SETTINGS = {
    "TITLE": "GLORYBELLE API",
    "DESCRIPTION": "Luxury Italian Jewelry E-Commerce — Backend API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "apps.orders.models.Order.STATUS_CHOICES",
        "EnquiryStatusEnum": "apps.enquiries.models.Enquiry.STATUS_CHOICES",
    },
}

# =============================================================================
# CORS
# =============================================================================
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000",
    cast=Csv(),
)
CORS_ALLOW_ALL_ORIGINS = False
if any("*" in origin for origin in CORS_ALLOWED_ORIGINS):
    raise ValueError("CORS_ALLOWED_ORIGINS must contain exact origins, not wildcards.")
CORS_ALLOW_CREDENTIALS = True
# X-Cart-Token identifies a guest cart without cookies (see apps/cart/guest.py).
from corsheaders.defaults import default_headers  # noqa: E402

CORS_ALLOW_HEADERS = (*default_headers, "x-cart-token")

# =============================================================================
# Celery
# =============================================================================
CELERY_BROKER_URL = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Europe/Rome"

# =============================================================================
# Stripe
# =============================================================================
STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = config("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")

# =============================================================================
# Fattura24 (Italian e-invoicing)
# =============================================================================
FATTURA24_API_KEY = config("FATTURA24_API_KEY", default="")
# P1 fix #15 — Fattura24 document template ID (configured in Fattura24 dashboard)
FATTURA24_TEMPLATE_ID = config("FATTURA24_TEMPLATE_ID", default="")

# =============================================================================
# SendGrid
# =============================================================================
SENDGRID_API_KEY = config("SENDGRID_API_KEY", default="")

# =============================================================================
# Stock reservation
# =============================================================================
STOCK_RESERVATION_MINUTES = 15

# =============================================================================
# Email
# =============================================================================
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=25, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10, cast=int)
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default="ordini@glorybelle.it",
)
ENQUIRY_NOTIFICATION_EMAIL = config(
    "ENQUIRY_NOTIFICATION_EMAIL",
    default=DEFAULT_FROM_EMAIL,
)

# =============================================================================
# django-unfold — branded admin (P1 fix #12)
# Per roadmap Day 9: install + brand admin with GLORYBELLE palette.
# design.md §2.1 palette: --ink #14201C, --ivory #F6F1E7, --gold #B9924F,
# --emerald-deep #132F26, --gold-light #E4C583
# =============================================================================
UNFOLD = {
    "SITE_TITLE": "GLORYBELLE Admin",
    "SITE_HEADER": "GLORYBELLE",
    "SITE_SYMBOL": "diamond",
    "SHOW_THEMES": False,
    "SHOW_LANGUAGES": True,
    "LANGUAGE_FLAGS": {
        "it": "🇮🇹",
        "en": "🇬🇧",
    },
    "DEFAULT_THEME": "light",
    "COLORS": {
        "primary": {
            "50": "#f6f1e7",   # ivory
            "100": "#efe7d6",  # ivory-2
            "400": "#b9924f",  # gold
            "500": "#8c6b33",  # gold-deep
            "600": "#7a5a2a",
            "700": "#5c441f",
            "800": "#3d2d14",
            "900": "#1f160a",
        },
        "accent": {
            "50": "#e8f0ed",
            "100": "#cfe3da",
            "400": "#1f4d3e",  # emerald
            "500": "#132f26",  # emerald-deep
            "600": "#0f2520",
            "700": "#0b1c19",
            "800": "#081412",
            "900": "#050c0b",
        },
    },
    "SIDEBAR": {
        "BG_COLOR": "#132f26",  # emerald-deep
        "NAV_COLOR": "#e6e1d3",  # warm light text
    },
}
FIRST_PURCHASE_DISCOUNT_PERCENT = Decimal("10.00")
FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL = Decimal("0.00")  # no minimum threshold