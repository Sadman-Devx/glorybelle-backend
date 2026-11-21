"""
GLORYBELLE — Catalog URL Configuration.

P1 fix #10: adds /api/search/ endpoint (uses ProductSearchView).
The /api/products/featured/ endpoint is registered automatically by
DRF router (because of the @action(detail=False) decorator on ProductViewSet).
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .search_view import ProductSearchView
from .views import CategoryViewSet, ProductViewSet

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")

urlpatterns = [
    # P1 fix #10 — search endpoint
    path("search/", ProductSearchView.as_view(), name="product-search"),
    path("", include(router.urls)),
]
