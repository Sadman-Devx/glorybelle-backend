"""
GLORYBELLE — Cart Serializers.
"""
from decimal import Decimal

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

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

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_primary_image(self, obj) -> str | None:
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
    discount = serializers.SerializerMethodField()
    total_after_discount = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "items",
            "total",
            "item_count",
            "discount",
            "total_after_discount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _welcome_discount(self, obj):
        """The discount this cart would get at checkout (same function the order uses)."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        if not hasattr(obj, "_welcome_discount_cache"):
            from apps.orders.services import compute_first_purchase_discount

            lines = [
                (item.variant.product.name, item.variant.price, item.quantity)
                for item in obj.items.select_related("variant__product")
            ]
            result = compute_first_purchase_discount(lines, user)
            obj._welcome_discount_cache = result if result.applies else None
        return obj._welcome_discount_cache

    def get_discount(self, obj) -> dict | None:
        found = self._welcome_discount(obj)
        if found is None:
            return None
        return {
            "percent": str(found.percent),
            "amount": str(found.amount),
            "product_name": found.product_name,
            "unit_price": str(found.unit_price),
        }

    def get_total_after_discount(self, obj) -> str:
        found = self._welcome_discount(obj)
        total = obj.total - found.amount if found else obj.total
        return str(Decimal(total).quantize(Decimal("0.01")))


class AddToCartSerializer(serializers.Serializer):
    """Input for adding an item to the cart."""

    variant_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    """Input for updating cart item quantity."""

    quantity = serializers.IntegerField(min_value=0)
