"""
GLORYBELLE — Order URL Configuration.
"""
from django.urls import path

from .views import CheckoutView, OrderDetailView, OrderHistoryView

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("orders/", OrderHistoryView.as_view(), name="order-history"),
    path(
        "orders/<str:order_number>/",
        OrderDetailView.as_view(),
        name="order-detail",
    ),
]
