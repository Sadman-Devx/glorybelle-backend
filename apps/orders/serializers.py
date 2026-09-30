"""
GLORYBELLE — Order Serializers.
"""
from rest_framework import serializers

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
    """Full order detail with all snapshotted items."""

    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
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
            # Totals
            "subtotal",
            "shipping_cost",
            "total",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrderListSerializer(serializers.ModelSerializer):
    """Lightweight order list for order history."""

    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_display",
            "total",
            "item_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_item_count(self, obj):
        return obj.items.count()


class CheckoutSerializer(serializers.Serializer):
    """
    Input for the checkout endpoint.

    Supports both saved address (by ID) and inline address data.
    Per PRD §3.2: guest checkout requires email but no account.
    """

    email = serializers.EmailField()
    notes = serializers.CharField(required=False, default="", allow_blank=True)

    # Shipping — either an ID or inline data
    shipping_address_id = serializers.IntegerField(required=False)
    shipping_address = serializers.DictField(required=False)

    # Billing
    billing_same_as_shipping = serializers.BooleanField(default=True)
    billing_address_id = serializers.IntegerField(required=False)
    billing_address = serializers.DictField(required=False)

    def validate(self, data):
        has_shipping_id = "shipping_address_id" in data
        has_shipping_data = "shipping_address" in data

        if not has_shipping_id and not has_shipping_data:
            raise serializers.ValidationError(
                {"shipping_address": "È necessario un indirizzo di spedizione."}
            )

        # Validate inline address fields if provided
        if has_shipping_data:
            required_fields = [
                "first_name", "last_name", "line1",
                "city", "province", "postal_code",
            ]
            for field in required_fields:
                if not data["shipping_address"].get(field):
                    raise serializers.ValidationError(
                        {f"shipping_address.{field}": "Questo campo è obbligatorio."}
                    )

        return data
