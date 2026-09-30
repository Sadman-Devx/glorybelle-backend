"""
GLORYBELLE — Cart Admin.
"""
from django.contrib import admin

from .models import Cart, CartItem, StockReservation


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("variant", "quantity", "line_total")

    def line_total(self, obj):
        return f"€{obj.line_total:.2f}"

    line_total.short_description = "Totale riga"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "item_count", "total_display", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "session_key")
    inlines = [CartItemInline]

    def total_display(self, obj):
        return f"€{obj.total:.2f}"

    total_display.short_description = "Totale"

    def item_count(self, obj):
        return obj.item_count

    item_count.short_description = "Articoli"


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "variant",
        "quantity",
        "is_active",
        "expires_at",
        "is_expired_display",
    )
    list_filter = ("is_active",)
    readonly_fields = ("cart_item", "variant", "quantity", "expires_at", "created_at")

    def is_expired_display(self, obj):
        return obj.is_expired

    is_expired_display.short_description = "Scaduta"
    is_expired_display.boolean = True
