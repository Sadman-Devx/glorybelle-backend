"""
GLORYBELLE — Invoice Admin.
"""
from django.contrib import admin

from .models import Invoice


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "order",
        "status",
        "fattura24_id",
        "attempts",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("invoice_number", "fattura24_id", "order__order_number")
    readonly_fields = (
        "order",
        "invoice_number",
        "fattura24_id",
        "status",
        "pdf_url",
        "xml_content",
        "error_message",
        "attempts",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        # Invoices are created by the Celery task, not admin
        return False
