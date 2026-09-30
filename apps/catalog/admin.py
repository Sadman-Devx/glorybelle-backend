"""
GLORYBELLE — Catalog Admin.

Per PRD §3.5: client-operable admin — clear "Add Product" / "Upload Photo"
flows. Product admin has inline variants and images with image previews.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product, ProductImage, ProductVariant


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = (
        "metal",
        "size",
        "sku",
        "price_override",
        "stock_quantity",
        "reserved_quantity",
        "is_active",
    )
    readonly_fields = ("reserved_quantity",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = (
        "image",
        "image_alt",
        "alt_text",
        "is_primary",
        "sort_order",
        "image_preview",
    )
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:80px; border-radius:4px;" />',
                obj.image.url,
            )
        return "—"

    image_preview.short_description = "Anteprima"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("sort_order", "is_active")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "base_price",
        "metal",
        "is_active",
        "is_featured",
        "variant_count",
        "primary_image_preview",
    )
    list_filter = ("category", "metal", "gem", "is_active", "is_featured")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("is_active", "is_featured")
    inlines = [ProductVariantInline, ProductImageInline]

    def variant_count(self, obj):
        return obj.variants.count()

    variant_count.short_description = "Varianti"

    def primary_image_preview(self, obj):
        img = obj.primary_image
        if img and img.image:
            return format_html(
                '<img src="{}" style="max-height:50px; border-radius:3px;" />',
                img.image.url,
            )
        return "—"

    primary_image_preview.short_description = "Foto"
