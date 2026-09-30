"""
GLORYBELLE — Wishlist Serializers.
"""
from rest_framework import serializers

from apps.catalog.serializers import ProductListSerializer

from .models import WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    """Wishlist item with full product details."""

    product_detail = ProductListSerializer(source="product", read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "product", "product_detail", "created_at"]
        read_only_fields = ["id", "product_detail", "created_at"]


class WishlistToggleSerializer(serializers.Serializer):
    """Input for toggling a product in the wishlist."""

    product_id = serializers.IntegerField()
