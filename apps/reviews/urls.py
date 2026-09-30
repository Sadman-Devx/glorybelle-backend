"""
GLORYBELLE — Review URL Configuration.
"""
from django.urls import path

from .views import ProductReviewCreateView, ProductReviewListView

urlpatterns = [
    path(
        "products/<slug:product_slug>/reviews/",
        ProductReviewListView.as_view(),
        name="product-reviews",
    ),
    path(
        "products/<slug:product_slug>/reviews/create/",
        ProductReviewCreateView.as_view(),
        name="product-review-create",
    ),
]
