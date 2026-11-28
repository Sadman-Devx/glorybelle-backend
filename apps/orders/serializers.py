"""
GLORYBELLE — Order Serializers.

P1 fix #8: idempotency_key exposed.
New: discount_percent + discount_amount fields in OrderSerializer + OrderListSerializer.
"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    """Read-only serializer for snapshotted order line items."""

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_name",
            "variant_metal",
            "variant_metal_display",
            "variant_size",
            "sku",
            "unit_price",
            "quantity",
            "line_total",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    """Full order detail with all snapshotted items + discount info."""

    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    has_discount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "idempotency_key",
            "email",
            "status",
            "status_display",
            # Shipping
            "shipping_first_name",
            "shipping_last_name",
            "shipping_line1",
            "shipping_line2",
            "shipping_city",
            "shipping_province",
            "shipping_postal_code",
            "shipping_country",
            # Billing
            "billing_first_name",
            "billing_last_name",
            "billing_line1",
            "billing_line2",
            "billing_city",
            "billing_province",
            "billing_postal_code",
            "billing_country",
            # Totals + discount
            "subtotal",
            "discount_percent",
            "discount_amount",
            "discount_product_name",
            "has_discount",
            "shipping_cost",
            "total",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.BooleanField())
    def get_has_discount(self, obj) -> bool:
        return obj.discount_amount > 0


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight order list for order history."""

    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    item_count = serializers.SerializerMethodField()
    has_discount = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_display",
            "subtotal",
            "discount_amount",
            "has_discount",
            "total",
            "item_count",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_item_count(self, obj) -> int:
        annotated = getattr(obj, "item_count_annotated", None)
        if annotated is not None:
            return annotated
        return obj.items.count()

    @extend_schema_field(serializers.BooleanField())
    def get_has_discount(self, obj) -> bool:
        return obj.discount_amount > 0


class CheckoutSerializer(serializers.Serializer):
    """Input for the checkout endpoint."""

    email = serializers.EmailField()
    notes = serializers.CharField(required=False, default="", allow_blank=True)
    idempotency_key = serializers.UUIDField(required=False)

    shipping_address_id = serializers.IntegerField(required=False)
    shipping_address = serializers.DictField(required=False)

    billing_same_as_shipping = serializers.BooleanField(default=True)
    billing_address_id = serializers.IntegerField(required=False)
    billing_address = serializers.DictField(required=False)

    # Max lengths mirror the Order model columns — longer input used to raise a
    # database error (HTTP 500) instead of a validation error.
    ADDRESS_LIMITS = {
        "first_name": 100, "last_name": 100, "line1": 255, "line2": 255,
        "city": 100, "province": 10, "postal_code": 10, "country": 2,
    }
    ADDRESS_REQUIRED = ["first_name", "last_name", "line1", "city", "province", "postal_code"]

    def _clean_address(self, raw, label):
        """Whitelist + bound an address dict; unknown keys (e.g. phone) are dropped."""
        if not isinstance(raw, dict):
            raise serializers.ValidationError({label: "Formato indirizzo non valido."})
        cleaned = {}
        for key, limit in self.ADDRESS_LIMITS.items():
            value = raw.get(key, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise serializers.ValidationError({f"{label}.{key}": "Deve essere un testo."})
            value = value.strip()
            if len(value) > limit:
                raise serializers.ValidationError(
                    {f"{label}.{key}": f"Massimo {limit} caratteri."}
                )
            cleaned[key] = value
        cleaned["country"] = (cleaned["country"] or "IT").upper()
        for field in self.ADDRESS_REQUIRED:
            if not cleaned[field]:
                raise serializers.ValidationError(
                    {f"{label}.{field}": "Questo campo è obbligatorio."}
                )
        return cleaned

    def validate(self, data):
        has_shipping_id = "shipping_address_id" in data
        has_shipping_data = "shipping_address" in data

        if not has_shipping_id and not has_shipping_data:
            raise serializers.ValidationError(
                {"shipping_address": "È necessario un indirizzo di spedizione."}
            )

        if has_shipping_data:
            data["shipping_address"] = self._clean_address(
                data["shipping_address"], "shipping_address"
            )
        if "billing_address" in data:
            data["billing_address"] = self._clean_address(
                data["billing_address"], "billing_address"
            )

        if not data.get("billing_same_as_shipping", True):
            if "billing_address_id" not in data and "billing_address" not in data:
                raise serializers.ValidationError(
                    {"billing_address": "È necessario un indirizzo di fatturazione."}
                )

        return data


class OrderGuestLookupSerializer(serializers.Serializer):
    """Input for POST /api/orders/lookup/ (guest order confirmation)."""

    order_number = serializers.CharField(max_length=30)
    email = serializers.EmailField()
