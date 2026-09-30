"""
GLORYBELLE — Payment Admin.
"""
from django.contrib import admin

from .models import Payment, ProcessedWebhookEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "stripe_payment_intent_id",
        "order",
        "amount_display",
        "status",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = (
        "stripe_payment_intent_id",
        "stripe_charge_id",
        "order__order_number",
    )
    readonly_fields = (
        "order",
        "stripe_payment_intent_id",
        "stripe_charge_id",
        "amount",
        "currency",
        "status",
        "idempotency_key",
        "created_at",
        "updated_at",
    )

    def amount_display(self, obj):
        return f"€{obj.amount:.2f}"

    amount_display.short_description = "Importo"
    amount_display.admin_order_field = "amount"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("stripe_event_id", "event_type", "processed_at")
    list_filter = ("event_type",)
    search_fields = ("stripe_event_id",)
    readonly_fields = ("stripe_event_id", "event_type", "processed_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
