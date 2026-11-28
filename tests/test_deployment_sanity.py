"""
Guards against the failures that only appear after deployment:
incompatible dependency pins and missing production configuration.
"""
from unittest.mock import patch

import pytest
import stripe
from django.conf import settings
from django.test import override_settings

from apps.payments import stripe_client
from config import checks


def test_celery_redis_transport_works_with_installed_versions():
    """
    kombu >= 5.7 refuses to work with redis-py < 6.1 (raises VersionMismatch the
    first time a task is sent). A plain `pip install -r requirements/*.txt` must
    always give a working pair, otherwise every .delay() call fails in production.
    """
    assert checks.redis_transport_problem() is None


def _ids(issues):
    return {i.id for i in issues}


GOOD = dict(
    STRIPE_SECRET_KEY="sk_test_abc", STRIPE_PUBLISHABLE_KEY="pk_test_abc", STRIPE_WEBHOOK_SECRET="whsec_abc",
    SENDGRID_API_KEY="SG.x", FATTURA24_API_KEY="f24", FRONTEND_URL="https://glorybelle.it",
    CORS_ALLOWED_ORIGINS=["https://glorybelle.it"],
)


@override_settings(**GOOD)
def test_valid_configuration_has_no_issues():
    assert checks.check_payment_configuration(None) == []
    assert checks.check_background_services(None) == []


@pytest.mark.parametrize("override,expected", [
    ({"STRIPE_SECRET_KEY": ""}, "glorybelle.E001"),
    ({"STRIPE_SECRET_KEY": "pk_test_oops"}, "glorybelle.E001"),
    ({"STRIPE_WEBHOOK_SECRET": ""}, "glorybelle.E002"),
    ({"STRIPE_PUBLISHABLE_KEY": ""}, "glorybelle.W001"),
    ({"STRIPE_SECRET_KEY": "sk_live_x", "STRIPE_PUBLISHABLE_KEY": "pk_test_x"}, "glorybelle.E003"),
    ({"STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_PUBLISHABLE_KEY": "pk_live_x"}, "glorybelle.E004"),
])
def test_payment_misconfiguration_is_reported(override, expected):
    with override_settings(**{**GOOD, **override}):
        assert expected in _ids(checks.check_payment_configuration(None))


@pytest.mark.parametrize("override,expected", [
    ({"SENDGRID_API_KEY": ""}, "glorybelle.W002"),
    ({"FATTURA24_API_KEY": ""}, "glorybelle.W003"),
    ({"FRONTEND_URL": "http://localhost:3000"}, "glorybelle.W004"),
    ({"CORS_ALLOWED_ORIGINS": ["http://localhost:3000"]}, "glorybelle.W005"),
])
def test_background_service_misconfiguration_is_reported(override, expected):
    with override_settings(**{**GOOD, **override}):
        assert expected in _ids(checks.check_background_services(None))


def test_broken_celery_transport_is_an_error():
    with override_settings(**GOOD, CELERY_BROKER_URL="redis://localhost:6379/0"), \
            patch.object(checks, "redis_transport_problem", return_value=RuntimeError("redis-py too old")):
        assert "glorybelle.E005" in _ids(checks.check_background_services(None))


def test_zero_num_proxies_warns_with_deployment_values():
    rest_framework = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    with override_settings(REST_FRAMEWORK=rest_framework):
        issues = checks.check_num_proxies(None)

    warning = next(issue for issue in issues if issue.id == "glorybelle.W006")
    assert "direct=0" in warning.hint
    assert "one reverse proxy (nginx/Traefik)=1" in warning.hint
    assert "Cloudflare + nginx=2" in warning.hint


@pytest.mark.parametrize("num_proxies", [1, 2])
def test_configured_num_proxies_does_not_warn(num_proxies):
    rest_framework = {**settings.REST_FRAMEWORK, "NUM_PROXIES": num_proxies}
    with override_settings(REST_FRAMEWORK=rest_framework):
        assert checks.check_num_proxies(None) == []


# ---- cancel_payment_intent: WHY it failed decides what the checkout does next
@pytest.mark.parametrize("error,retryable", [
    (stripe.error.APIConnectionError("network down"), True),
    (stripe.error.APIError("stripe 500"), True),
    (stripe.error.RateLimitError("slow down"), True),
    (stripe.error.InvalidRequestError("status is succeeded", param=None), False),
    (stripe.error.AuthenticationError("bad key"), False),
])
def test_cancel_failure_reports_whether_it_is_retryable(error, retryable):
    with patch.object(stripe.PaymentIntent, "cancel", side_effect=error):
        with pytest.raises(stripe_client.PaymentIntentNotCancellable) as exc:
            stripe_client.cancel_payment_intent("pi_x")
    assert exc.value.retryable is retryable


def test_cancel_of_a_missing_payment_intent_counts_as_cancelled():
    err = stripe.error.InvalidRequestError("No such payment_intent", param=None, code="resource_missing")
    with patch.object(stripe.PaymentIntent, "cancel", side_effect=err):
        stripe_client.cancel_payment_intent("pi_gone")  # must not raise
