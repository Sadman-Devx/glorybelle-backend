"""
GLORYBELLE — Catalog Views.

Thin HTTP adapter — no business logic here (rule.md).
Per rule.md: use select_related / prefetch_related to avoid N+1.

P1 fix #10: adds GET /api/products/featured/ as a dedicated endpoint (was
previously only available via ?featured=true filter).

P1 fix #14: CategoryViewSet and ProductViewSet now actually USE the cache
helpers from core/cache.py (previously dead code). Cache TTLs:
  - product list: 5 min (300s)
  - product detail: 10 min (600s)
  - category list: 5 min
Cache invalidation is signal-driven (catalog/signals.py on save/delete).
"""
import logging

from django.conf import settings
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.cache import (
    CATEGORY_LIST_PREFIX,
    PRODUCT_DETAIL_PREFIX,
    PRODUCT_LIST_PREFIX,
    get_cached,
    make_cache_key,
    set_cached,
)

from .filters import ProductFilter
from .models import Category, Product
from .serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)

logger = logging.getLogger(__name__)

PRODUCT_LIST_TTL = 300       # 5 minutes (architecture.md §6.7)
PRODUCT_DETAIL_TTL = 600     # 10 minutes
CATEGORY_LIST_TTL = 300      # 5 minutes


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve product categories.

    GET /api/categories/         → list all active categories
    GET /api/categories/{slug}/  → category detail
    """

    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return Category.objects.filter(is_active=True).prefetch_related("products")

    def list(self, request, *args, **kwargs):
        """List categories — cached (P1 fix #14)."""
        cache_key = make_cache_key(
            CATEGORY_LIST_PREFIX,
            page=request.query_params.get("page", "1"),
            page_size=request.query_params.get("page_size"),
        )
        cached_response = get_cached(cache_key)
        if cached_response is not None:
            logger.debug("Cache HIT for %s", cache_key)
            return Response(cached_response)

        response = super().list(request, *args, **kwargs)
        set_cached(cache_key, response.data, ttl=CATEGORY_LIST_TTL)
        logger.debug("Cache MISS for %s — set with TTL %ss", cache_key, CATEGORY_LIST_TTL)
        return response


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve products with filtering and pagination.

    GET /api/products/                              → paginated product list
    GET /api/products/?category=anelli&metal=silver  → filtered
    GET /api/products/?featured=true                 → featured only (still works)
    GET /api/products/featured/                     → featured only (P1 fix #10 — dedicated endpoint)
    GET /api/products/{slug}/                        → product detail
    """

    permission_classes = [AllowAny]
    filterset_class = ProductFilter
    lookup_field = "slug"
    ordering_fields = ["base_price", "created_at", "name"]
    ordering = ["-created_at"]
    search_fields = ["name", "description"]

    def get_queryset(self):
        """Active products with related data prefetched."""
        return (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images__media_asset")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def list(self, request, *args, **kwargs):
        """List products — cached per filter combination (P1 fix #14)."""
        # Build a cache key from all filter parameters
        # Every parameter that changes the RESULT must be in the key — including
        # page_size, otherwise ?page_size=100 is served the cached 8-item page.
        # Only known parameters are used so random query strings cannot flood the cache.
        key_params = set(ProductFilter.base_filters) | {
            "search", "ordering", "page", "page_size",
        }
        cache_key = make_cache_key(
            PRODUCT_LIST_PREFIX,
            **{name: request.query_params.get(name) for name in key_params},
        )
        cached_response = get_cached(cache_key)
        if cached_response is not None:
            logger.debug("Cache HIT for %s", cache_key)
            return Response(cached_response)

        response = super().list(request, *args, **kwargs)
        set_cached(cache_key, response.data, ttl=PRODUCT_LIST_TTL)
        logger.debug("Cache MISS for %s — set with TTL %ss", cache_key, PRODUCT_LIST_TTL)
        return response

    def retrieve(self, request, *args, **kwargs):
        """Retrieve single product — cached per slug (P1 fix #14)."""
        slug = kwargs.get(self.lookup_field)
        cache_key = make_cache_key(PRODUCT_DETAIL_PREFIX, slug=slug)
        cached_response = get_cached(cache_key)
        if cached_response is not None:
            logger.debug("Cache HIT for %s", cache_key)
            return Response(cached_response)

        response = super().retrieve(request, *args, **kwargs)
        set_cached(cache_key, response.data, ttl=PRODUCT_DETAIL_TTL)
        logger.debug("Cache MISS for %s — set with TTL %ss", cache_key, PRODUCT_DETAIL_TTL)
        return response

    @action(detail=False, methods=["get"], url_path="featured")
    def featured(self, request):
        """
        GET /api/products/featured/

        Returns the paginated list of featured products (is_featured=True).
        P1 fix #10 — dedicated endpoint so the frontend doesn't need to pass
        ?featured=true as a filter (cleaner contract).
        """
        queryset = self.get_queryset().filter(is_featured=True)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
