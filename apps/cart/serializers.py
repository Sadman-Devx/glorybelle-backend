"""
GLORYBELLE — Cart Serializers.
"""
from rest_framework import serializers

from apps.catalog.serializers import ProductVariantSerializer

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    """Cart line item with variant details and line total."""

    variant_detail = ProductVariantSerializer(source="variant", read_only=True)
    product_name = serializers.CharField(
        source="variant.product.name", read_only=True
    )
    product_slug = serializers.CharField(
        source="variant.product.slug", read_only=True
    )
    line_total = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "variant",
            "variant_detail",
            "product_name",
            "product_slug",
            "quantity",
            "line_total",
            "primary_image",
        ]
        read_only_fields = [
            "id",
            "variant_detail",
            "product_name",
            "product_slug",
            "line_total",
            "primary_image",
        ]

    def get_primary_image(self, obj):
        img = obj.variant.product.primary_image
        if img and img.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(img.image.url)
        return None


class CartSerializer(serializers.ModelSerializer):
    """Full cart with items, total, and item count."""

    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            "id",
            "items",
            "total",
            "item_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AddToCartSerializer(serializers.Serializer):
    """Input for adding an item to the cart."""

    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    """Input for updating cart item quantity."""

    quantity = serializers.IntegerField(min_value=0)
