from copy import deepcopy

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from .views import LoginView


LOGIN_URL = "/api/accounts/login/"
LOGIN_PAYLOAD = {"email": "missing@glorybelle.test", "password": "invalid"}


def _rest_framework_with_num_proxies(num_proxies):
    rest_framework = deepcopy(settings.REST_FRAMEWORK)
    rest_framework["NUM_PROXIES"] = num_proxies
    return rest_framework


def _login_is_allowed(throttle, factory, forwarded_for, remote_addr="10.0.0.1"):
    request = Request(
        factory.post(
            LOGIN_URL,
            LOGIN_PAYLOAD,
            REMOTE_ADDR=remote_addr,
            HTTP_X_FORWARDED_FOR=forwarded_for,
        ),
        authenticators=[],
    )
    return throttle.allow_request(request, LoginView())


def test_login_throttle_uses_the_configured_proxy_hop_and_resists_spoofing():
    with override_settings(
        REST_FRAMEWORK=_rest_framework_with_num_proxies(1)
    ):
        cache.clear()
        factory = APIRequestFactory()
        throttle = LoginView.throttle_classes[0]()
        for _ in range(10):
            assert _login_is_allowed(throttle, factory, "198.51.100.10")

        assert _login_is_allowed(throttle, factory, "198.51.100.11")
        assert not _login_is_allowed(
            throttle,
            factory,
            "203.0.113.99, 198.51.100.10",
        )


def test_login_throttle_ignores_forwarded_for_with_zero_proxies():
    with override_settings(
        REST_FRAMEWORK=_rest_framework_with_num_proxies(0)
    ):
        cache.clear()
        factory = APIRequestFactory()
        throttle = LoginView.throttle_classes[0]()

        for _ in range(10):
            assert _login_is_allowed(throttle, factory, "198.51.100.10")

        assert not _login_is_allowed(throttle, factory, "198.51.100.11")
        assert _login_is_allowed(
            throttle,
            factory,
            "198.51.100.11",
            remote_addr="10.0.0.2",
        )


def test_num_proxies_setting_is_wired_into_rest_framework():
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == settings.NUM_PROXIES
