# =============================================================================
# GLORYBELLE — Backend Dockerfile
# Multi-stage: build deps in `builder`, copy to slim `runner` image.
# One image is used for the web app, the Celery worker and Celery beat — only
# the command differs (see docker-compose.yml).
# =============================================================================

# ---- Builder stage ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build tools for wheels that may need compiling (Pillow, psycopg2 fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps into a single prefix we can copy later.
# Copied first so this layer is cached until requirements change.
COPY requirements/ /app/requirements/
RUN pip install --prefix=/install -r /app/requirements/production.txt


# ---- Runner stage ----
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    WEB_CONCURRENCY=4

# Runtime system deps only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — the app never needs root
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

WORKDIR /app

# Application code (see .dockerignore — .env, .git, tests, *.sqlite3 are excluded)
COPY --chown=app:app . /app/

# Writable dirs for the non-root user. /app/media is the mount point of the
# `media_files` volume; creating it here makes the volume inherit this owner.
RUN mkdir -p /app/media /app/staticfiles \
    && chown -R app:app /app/media /app/staticfiles

USER app

# Collect static files at build time (served by WhiteNoise). Settings need a
# few required vars at import time; these are throw-away build values and are
# NOT baked into the runtime environment.
RUN SECRET_KEY=build-only-not-a-secret \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Healthcheck — /health/ runs `SELECT 1`; plain python avoids installing curl.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/', timeout=5)" || exit 1

# Worker count comes from WEB_CONCURRENCY (gunicorn reads it natively).
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "config.wsgi:application"]
