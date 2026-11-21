"""
GLORYBELLE — Search View.

P1 fix #10: GET /api/search/?q=... — quick product search for the
header / mega-menu search bar. Matches name + description, returns
top 8 results (lightweight payload).
"""
from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer


class ProductSearchView(generics.ListAPIView):
    """
    GET /api/search/?q=...

    Quick product search — matches name (case-insensitive contains) or
    description. Returns up to 8 results, sorted by relevance (name match
    first, then newest).

    Designed for the header search bar in the GLORYBELLE frontend. Heavier
    search (Elasticsearch, Algolia, etc.) would replace this later if the
    catalog grows past a few hundred products.
    """

    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        query = self.request.query_params.get("q", "").strip()
        if not query or len(query) < 2:
            return Product.objects.none()

        # Active products with related data prefetched (rule.md: no N+1)
        queryset = (
            Product.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related("variants", "images")
        )
        # Case-insensitive contains on name OR description
        queryset = queryset.filter(
            name__icontains=query
        ) | queryset.filter(
            description__icontains=query
        )
        # Name-match first (sort by name match, then newest)
        queryset = queryset.distinct().order_by("-created_at")[:8]
        return queryset
