# =============================================================================
# GLORYBELLE — Backend Dockerfile
# Multi-stage: build deps in `builder`, copy to slim `runner` image
# =============================================================================

# ---- Builder stage ----
FROM python:3.12-slim AS builder

# System deps needed to compile psycopg2, Pillow
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps to a single prefix we can copy later
COPY requirements/ /app/requirements/
RUN pip install --prefix=/install -r /app/requirements/production.txt


# ---- Runner stage ----
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# Runtime system deps (libpq only — no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application code
COPY . /app/

# Collect static (needed for admin to work in production)
RUN python manage.py collectstatic --noinput

# Run gunicorn on port 8000
EXPOSE 8000

# Healthcheck — ping Django via curl-equivalent (using python to avoid extra dep)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/api/schema/').status == 200 else sys.exit(1)"

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2", "--timeout", "60", "config.wsgi:application"]
