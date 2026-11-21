"""
GLORYBELLE — Wishlist URL Configuration.

P1 fix #10: adds DELETE /api/wishlist/items/{product_id}/ endpoint.
"""
from django.urls import path

from .views import (
    WishlistItemDetailView,
    WishlistListView,
    WishlistToggleView,
)

urlpatterns = [
    path("wishlist/", WishlistListView.as_view(), name="wishlist-list"),
    path("wishlist/toggle/", WishlistToggleView.as_view(), name="wishlist-toggle"),
    # P1 fix #10 — explicit DELETE endpoint (spec compliance)
    path(
        "wishlist/items/<int:product_id>/",
        WishlistItemDetailView.as_view(),
        name="wishlist-item-detail",
    ),
]
