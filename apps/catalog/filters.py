"""
GLORYBELLE — Catalog Filters.

django-filter FilterSet: category, metal, gem, price range.
Per roadmap Day 3: GET /api/products/?category=anelli&metal=argento
"""
import django_filters

from .models import Product


class ProductFilter(django_filters.FilterSet):
    """
    Filterable product listing.

    Supports:
      - category (by slug): ?category=anelli
      - metal: ?metal=gold
      - gem: ?gem=diamond
      - min_price / max_price: ?min_price=50&max_price=200
      - featured: ?featured=true
    """

    category = django_filters.CharFilter(
        field_name="category__slug",
        lookup_expr="exact",
        label="Categoria (slug)",
    )
    metal = django_filters.CharFilter(
        field_name="metal",
        lookup_expr="exact",
        label="Metallo",
    )
    gem = django_filters.CharFilter(
        field_name="gem",
        lookup_expr="exact",
        label="Pietra",
    )
    min_price = django_filters.NumberFilter(
        field_name="base_price",
        lookup_expr="gte",
        label="Prezzo minimo",
    )
    max_price = django_filters.NumberFilter(
        field_name="base_price",
        lookup_expr="lte",
        label="Prezzo massimo",
    )
    featured = django_filters.BooleanFilter(
        field_name="is_featured",
        label="In evidenza",
    )

    class Meta:
        model = Product
        fields = ["category", "metal", "gem", "min_price", "max_price", "featured"]
