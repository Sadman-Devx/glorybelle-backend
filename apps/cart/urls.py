"""
GLORYBELLE — Cart URL Configuration.
"""
from django.urls import path

from .views import CartItemView, CartMergeView, CartView

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path(
        "cart/items/",
        CartItemView.as_view(http_method_names=["post", "options"]),
        name="cart-item-add",
    ),
    path(
        "cart/items/<int:item_id>/",
        CartItemView.as_view(http_method_names=["patch", "delete", "options"]),
        name="cart-item-detail",
    ),
    path("cart/merge/", CartMergeView.as_view(), name="cart-merge"),
]
