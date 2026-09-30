"""
GLORYBELLE — Order Admin.

Per PRD §3.5: clear order status display, read-only for order data.
"""
from django.contrib import admin

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "variant_metal_display",
        "variant_size",
        "sku",
        "unit_price",
        "quantity",
        "line_total",
    )
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "email",
        "status",
        "total_display",
        "item_count",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "email", "user__username")
    readonly_fields = (
        "order_number",
        "user",
        "email",
        "status",
        "subtotal",
        "shipping_cost",
        "total",
        "stripe_payment_intent_id",
        "shipping_first_name",
        "shipping_last_name",
        "shipping_line1",
        "shipping_line2",
        "shipping_city",
        "shipping_province",
        "shipping_postal_code",
        "shipping_country",
        "billing_first_name",
        "billing_last_name",
        "billing_line1",
        "billing_line2",
        "billing_city",
        "billing_province",
        "billing_postal_code",
        "billing_country",
        "notes",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]
    list_per_page = 25

    fieldsets = (
        ("Ordine", {
            "fields": (
                "order_number", "user", "email", "status",
                "stripe_payment_intent_id", "notes",
            ),
        }),
        ("Totali", {
            "fields": ("subtotal", "shipping_cost", "total"),
        }),
        ("Spedizione", {
            "fields": (
                "shipping_first_name", "shipping_last_name",
                "shipping_line1", "shipping_line2",
                "shipping_city", "shipping_province",
                "shipping_postal_code", "shipping_country",
            ),
        }),
        ("Fatturazione", {
            "fields": (
                "billing_first_name", "billing_last_name",
                "billing_line1", "billing_line2",
                "billing_city", "billing_province",
                "billing_postal_code", "billing_country",
            ),
            "classes": ("collapse",),
        }),
    )

    def total_display(self, obj):
        return f"€{obj.total:.2f}"

    total_display.short_description = "Totale"
    total_display.admin_order_field = "total"

    def item_count(self, obj):
        return obj.items.count()

    item_count.short_description = "Articoli"

    def has_add_permission(self, request):
        # Orders are created via checkout, not admin
        return False

    def has_delete_permission(self, request, obj=None):
        return False
