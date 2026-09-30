"""
GLORYBELLE — Payment URL Configuration.
"""
from django.urls import path

from .views import stripe_webhook_view

urlpatterns = [
    path("webhooks/stripe/", stripe_webhook_view, name="stripe-webhook"),
]
