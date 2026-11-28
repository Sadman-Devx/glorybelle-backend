"""
GLORYBELLE — Newsletter URL Configuration.
"""
from django.urls import path

from .views import (
    NewsletterConfirmView,
    NewsletterSubscribeView,
    NewsletterUnsubscribeView,
)

urlpatterns = [
    path(
        "newsletter/subscribe/",
        NewsletterSubscribeView.as_view(),
        name="newsletter-subscribe",
    ),
    path(
        "newsletter/unsubscribe/",
        NewsletterUnsubscribeView.as_view(),
        name="newsletter-unsubscribe",
    ),
    path(
        "newsletter/confirm/",
        NewsletterConfirmView.as_view(),
        name="newsletter-confirm",
    ),
]
