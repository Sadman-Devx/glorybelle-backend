from rest_framework import serializers
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from apps.orders.models import Order, OrderAdminNote, OrderItem
from apps.payments.models import Payment


class AdminCustomerSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()


class AdminAddressSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    line1 = serializers.CharField()
    line2 = serializers.CharField(allow_blank=True)
    city = serializers.CharField()
    province = serializers.CharField()
    postal_code = serializers.CharField()
    country = serializers.CharField()


class AdminOrderListSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="order_number", read_only=True)
    date = serializers.DateTimeField(source="created_at", read_only=True)
    customer = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = ("id", "number", "date", "customer", "total", "status", "item_count")
        read_only_fields = fields

    @extend_schema_field(AdminCustomerSerializer)
    def get_customer(self, order):
        return {
            "name": f"{order.shipping_first_name} {order.shipping_last_name}".strip(),
            "email": order.email,
        }


class AdminOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product_name",
            "variant_metal_display",
            "variant_size",
            "sku",
            "unit_price",
            "quantity",
            "line_total",
        )
        read_only_fields = fields


class AdminPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "status",
            "amount",
            "currency",
            "stripe_payment_intent_id",
            "stripe_charge_id",
            "stripe_refund_id",
            "stripe_refund_status",
            "updated_at",
        )
        read_only_fields = fields


class AdminOrderHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField(source="history_id", read_only=True)
    timestamp = serializers.DateTimeField(source="history_date", read_only=True)
    action = serializers.CharField(source="history_type", read_only=True)
    status = serializers.CharField(read_only=True)
    actor_id = serializers.IntegerField(source="history_user_id", read_only=True, allow_null=True)
    actor_email = serializers.SerializerMethodField()
    reason = serializers.CharField(
        source="history_change_reason",
        read_only=True,
        allow_null=True,
        allow_blank=True,
    )

    @extend_schema_field(OpenApiTypes.EMAIL)
    def get_actor_email(self, record) -> str | None:
        return record.history_user.email if record.history_user else None


class AdminOrderNoteSerializer(serializers.ModelSerializer):
    author_id = serializers.IntegerField(read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderAdminNote
        fields = ("id", "body", "author_id", "author_name", "created_at")
        read_only_fields = ("id", "author_id", "author_name", "created_at")

    @extend_schema_field(OpenApiTypes.STR)
    def get_author_name(self, note) -> str | None:
        if note.author is None:
            return None
        return note.author.get_full_name().strip() or note.author.get_username()


class AdminOrderNoteCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, trim_whitespace=True)


class AdminOrderDetailSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="order_number", read_only=True)
    customer = serializers.SerializerMethodField()
    items = AdminOrderItemSerializer(many=True, read_only=True)
    shipping_address = serializers.SerializerMethodField()
    billing_address = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()
    status_history = serializers.SerializerMethodField()
    internal_notes = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "created_at",
            "updated_at",
            "customer",
            "status",
            "total",
            "subtotal",
            "discount_amount",
            "shipping_cost",
            "tracking_number",
            "archived_at",
            "archive_reason",
            "shipping_address",
            "billing_address",
            "payment",
            "items",
            "status_history",
            "internal_notes",
        )
        read_only_fields = fields

    @extend_schema_field(AdminCustomerSerializer)
    def get_customer(self, order):
        return {
            "name": f"{order.shipping_first_name} {order.shipping_last_name}".strip(),
            "email": order.email,
        }

    @staticmethod
    def _address(order, prefix):
        return {
            "first_name": getattr(order, f"{prefix}_first_name"),
            "last_name": getattr(order, f"{prefix}_last_name"),
            "line1": getattr(order, f"{prefix}_line1"),
            "line2": getattr(order, f"{prefix}_line2"),
            "city": getattr(order, f"{prefix}_city"),
            "province": getattr(order, f"{prefix}_province"),
            "postal_code": getattr(order, f"{prefix}_postal_code"),
            "country": getattr(order, f"{prefix}_country"),
        }

    @extend_schema_field(AdminAddressSerializer)
    def get_shipping_address(self, order):
        return self._address(order, "shipping")

    @extend_schema_field(AdminAddressSerializer)
    def get_billing_address(self, order):
        return self._address(order, "billing")

    @extend_schema_field(AdminPaymentSerializer(allow_null=True))
    def get_payment(self, order):
        try:
            payment = order.payment
        except Payment.DoesNotExist:
            return None
        return AdminPaymentSerializer(payment).data

    @extend_schema_field(AdminOrderHistorySerializer(many=True))
    def get_status_history(self, order):
        records = order.history.select_related("history_user").order_by(
            "-history_date", "-history_id"
        )
        return AdminOrderHistorySerializer(records, many=True).data

    @extend_schema_field(AdminOrderNoteSerializer(many=True))
    def get_internal_notes(self, order):
        notes = order.admin_notes.select_related("author").all()
        return AdminOrderNoteSerializer(notes, many=True).data


class AdminOrderTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    tracking_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate(self, attrs):
        if "tracking_number" in attrs and attrs["status"] != "shipped":
            raise serializers.ValidationError(
                {"tracking_number": "È consentito solo quando lo stato diventa spedito."}
            )
        return attrs


class AdminOrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class AdminOrderArchiveSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class AdminOrderAuditEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.CharField()
    timestamp = serializers.DateTimeField()
    actor_id = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True, allow_null=True)


class AdminOrderActionResponseSerializer(serializers.Serializer):
    order = AdminOrderDetailSerializer()
    audit_event = AdminOrderAuditEventSerializer()


class AdminOrderStatusCountSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    count = serializers.IntegerField()


class AdminLowStockVariantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()
    metal = serializers.CharField()
    size = serializers.CharField()
    stock_quantity = serializers.IntegerField()
    reserved_quantity = serializers.IntegerField()
    available_stock = serializers.IntegerField()


class AdminDashboardSerializer(serializers.Serializer):
    today_orders = serializers.IntegerField()
    revenue_last_7_days = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_last_30_days = serializers.DecimalField(max_digits=12, decimal_places=2)
    orders_by_status = AdminOrderStatusCountSerializer(many=True)
    low_stock_variants = AdminLowStockVariantSerializer(many=True)
