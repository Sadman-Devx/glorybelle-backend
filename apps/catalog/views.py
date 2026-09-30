"""
GLORYBELLE — Catalog Views.

Thin HTTP adapter — no business logic here (rule.md).
Per rule.md: use select_related / prefetch_related to avoid N+1.
"""
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .filters import ProductFilter
from .models import Category, Product
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve product categories.

    GET /api/categories/         → list all active categories
    GET /api/categories/{slug}/  → category detail
    """

    queryset = Category.objects.filter(is_active=True).prefetch_related("products")
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve products with filtering and pagination.

    GET /api/products/                              → paginated product list
    GET /api/products/?category=anelli&metal=silver  → filtered
    GET /api/products/?featured=true                 → featured only
    GET /api/products/{slug}/                        → product detail
    """

    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    lookup_field = "slug"
    ordering_fields = ["base_price", "created_at", "name"]
    ordering = ["-created_at"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        """
        Active products with related data prefetched.
        Per rule.md: select_related / prefetch_related mandatory on list endpoints.
        """
        return (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related(
                "variants",
                "images",
            )
        )

    def get_serializer_class(self):
        """Use lightweight serializer for list, full for detail."""
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer
