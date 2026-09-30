"""
GLORYBELLE — Wishlist URL Configuration.
"""
from django.urls import path

from .views import WishlistListView, WishlistToggleView

urlpatterns = [
    path("wishlist/", WishlistListView.as_view(), name="wishlist-list"),
    path("wishlist/toggle/", WishlistToggleView.as_view(), name="wishlist-toggle"),
]
