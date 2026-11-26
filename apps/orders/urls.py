"""
GLORYBELLE — Order URL Configuration.
"""
from django.urls import path

from .views import (
    CheckoutView,
    OrderDetailView,
    OrderGuestLookupView,
    OrderHistoryView,
)

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderHistoryView.as_view(), name="order-history"),
    # Must stay BEFORE orders/<order_number>/ or "lookup" is captured as an order number.
    path("orders/lookup/", OrderGuestLookupView.as_view(), name="order-guest-lookup"),
    path(
        "orders/<str:order_number>/",
        OrderDetailView.as_view(),
        name="order-detail",
    ),
]
