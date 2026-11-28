"""
Deployment checks — run with:  python manage.py check --deploy

Catches the configuration mistakes that otherwise only show up as a silent
production failure (no card field, orders never marked paid, no emails).
Nothing here runs in development or tests unless called explicitly.
"""
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

LOCAL_HINTS = ("localhost", "127.0.0.1")


@register(Tags.security, deploy=True)
def check_num_proxies(app_configs, **kwargs):
    if settings.REST_FRAMEWORK.get("NUM_PROXIES", 0) != 0:
        return []
    return [Warning(
        "NUM_PROXIES is 0; forwarded client addresses are ignored. This is correct "
        "for direct traffic, but traffic behind a proxy will share its IP rate-limit bucket.",
        hint=(
            "Set NUM_PROXIES to the trusted hop count: direct=0, "
            "one reverse proxy (nginx/Traefik)=1, Cloudflare + nginx=2. "
            "Ensure trusted proxies append/sanitize X-Forwarded-For."
        ),
        id="glorybelle.W006",
    )]


def redis_transport_problem():
    """
    Return the exception kombu raises when its Redis transport cannot be used with the
    installed redis-py (e.g. kombu 5.7 + redis-py < 6.1), or None when it is fine.

    kombu only performs this check lazily — the first time a task is sent — so a
    broken install looks healthy until the first order is paid. No connection to
    Redis is made here.
    """
    from types import SimpleNamespace

    try:
        from kombu.transport.redis import Channel

        Channel._get_client(SimpleNamespace(global_keyprefix=""))
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


@register(Tags.security, deploy=True)
def check_payment_configuration(app_configs, **kwargs):
    issues = []
    secret = settings.STRIPE_SECRET_KEY
    webhook = settings.STRIPE_WEBHOOK_SECRET
    publishable = settings.STRIPE_PUBLISHABLE_KEY

    if not secret.startswith(("sk_", "rk_")):
        issues.append(Error(
            "STRIPE_SECRET_KEY is missing or is not a Stripe secret key (sk_...).",
            hint="Checkout cannot create PaymentIntents without it.",
            id="glorybelle.E001",
        ))
    if not webhook.startswith("whsec_"):
        issues.append(Error(
            "STRIPE_WEBHOOK_SECRET is missing or does not start with whsec_.",
            hint="Without it every Stripe webhook is rejected, so paid orders stay 'pending' forever.",
            id="glorybelle.E002",
        ))
    if not publishable.startswith("pk_"):
        issues.append(Warning(
            "STRIPE_PUBLISHABLE_KEY is missing or is not a publishable key (pk_...).",
            hint="The storefront needs the same key as NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY.",
            id="glorybelle.W001",
        ))
    if secret.startswith("sk_live_") and publishable.startswith("pk_test_"):
        issues.append(Error(
            "STRIPE_SECRET_KEY is LIVE but STRIPE_PUBLISHABLE_KEY is a TEST key.",
            hint="Card payments created in the browser would never match the server's account.",
            id="glorybelle.E003",
        ))
    if secret.startswith("sk_test_") and publishable.startswith("pk_live_"):
        issues.append(Error(
            "STRIPE_SECRET_KEY is a TEST key but STRIPE_PUBLISHABLE_KEY is LIVE.",
            id="glorybelle.E004",
        ))
    return issues


@register(Tags.security, deploy=True)
def check_background_services(app_configs, **kwargs):
    issues = []
    if not settings.SENDGRID_API_KEY:
        issues.append(Warning(
            "SENDGRID_API_KEY is not set: order confirmation emails will fail.",
            id="glorybelle.W002",
        ))
    if not settings.FATTURA24_API_KEY:
        issues.append(Warning(
            "FATTURA24_API_KEY is not set: electronic invoices will not be generated.",
            id="glorybelle.W003",
        ))
    if any(hint in settings.FRONTEND_URL for hint in LOCAL_HINTS):
        issues.append(Warning(
            f"FRONTEND_URL is {settings.FRONTEND_URL!r}: links in emails (password reset, ...) point to localhost.",
            id="glorybelle.W004",
        ))
    if all(any(hint in origin for hint in LOCAL_HINTS) for origin in settings.CORS_ALLOWED_ORIGINS):
        issues.append(Warning(
            "CORS_ALLOWED_ORIGINS only lists localhost origins: the production storefront will be blocked by CORS.",
            id="glorybelle.W005",
        ))

    # The Celery broker transport must be usable with the installed redis-py.
    if settings.CELERY_BROKER_URL.startswith(("redis://", "rediss://")):
        problem = redis_transport_problem()
        if problem is not None:
            issues.append(Error(
                f"Celery's Redis transport is unusable: {problem}",
                hint="Reinstall dependencies: pip install -r requirements/production.txt (redis>=6.1,<7).",
                id="glorybelle.E005",
            ))
    return issues
