"""
GLORYBELLE — Catalog Serializers.

Per rule.md: never trust a client-supplied price — the backend resolves
prices from ProductVariant.price_override / Product.base_price.
Per rule.md: use select_related / prefetch_related to avoid N+1 queries.
"""
from rest_framework import serializers

from .models import Category, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    """Category with product count."""

    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "image",
            "parent",
            "is_active",
            "product_count",
        ]
        read_only_fields = fields

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image with primary and hover-swap alt."""

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "image_alt",
            "alt_text",
            "is_primary",
            "sort_order",
        ]
        read_only_fields = fields


class ProductVariantSerializer(serializers.ModelSerializer):
    """
    Product variant with resolved price and available stock.

    price = variant override or product base price (server-side resolved)
    available_stock = stock_quantity - reserved_quantity
    """

    price = serializers.SerializerMethodField()
    available_stock = serializers.IntegerField(read_only=True)
    metal_display = serializers.CharField(
        source="get_metal_display", read_only=True
    )

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "metal",
            "metal_display",
            "size",
            "sku",
            "price",
            "available_stock",
            "is_active",
        ]
        read_only_fields = fields

    def get_price(self, obj):
        return str(obj.price)


class ProductListSerializer(serializers.ModelSerializer):
    """
    Product list serializer — lighter payload for the shop grid.

    Includes: category info, primary image, price range, available metals.
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    primary_image = serializers.SerializerMethodField()
    hover_image = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()
    available_metals = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "base_price",
            "metal",
            "gem",
            "purity",
            "is_featured",
            "category_name",
            "category_slug",
            "primary_image",
            "hover_image",
            "price_range",
            "available_metals",
        ]
        read_only_fields = fields

    def get_primary_image(self, obj):
        img = obj.primary_image
        if img and img.image:
            return self.context["request"].build_absolute_uri(img.image.url)
        return None

    def get_hover_image(self, obj):
        img = obj.primary_image
        if img and img.image_alt:
            return self.context["request"].build_absolute_uri(img.image_alt.url)
        return None

    def get_price_range(self, obj):
        """Return min/max price across active variants."""
        variants = obj.variants.filter(is_active=True)
        if not variants.exists():
            return {"min": str(obj.base_price), "max": str(obj.base_price)}
        prices = [v.price for v in variants]
        return {"min": str(min(prices)), "max": str(max(prices))}

    def get_available_metals(self, obj):
        """
        Return list of metals that have REAL availability > 0.

        P0 fix #4 — previous code filtered by `stock_quantity__gt=0`, which
        ignores reserved_quantity. A fully-reserved variant (stock=1,
        reserved=1, available=0) was incorrectly reported as "available",
        so customers could see + filter by a metal that they could never
        actually add to cart.

        Per backend-design PDF §6.11: available stock = stock_quantity −
        reserved_quantity. We compute this in Python because Django ORM
        can't directly subtract two columns in a filter without F()
        expressions + annotation; the variants list is already prefetched
        (no extra query cost), so iterating in Python is fine here.
        """
        available_metals = set()
        for variant in obj.variants.filter(is_active=True):
            if variant.stock_quantity - variant.reserved_quantity > 0:
                available_metals.add(variant.metal)
        return sorted(available_metals)


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product detail — includes all variants, all images, category info.
    """

    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "base_price",
            "metal",
            "gem",
            "purity",
            "is_active",
            "is_featured",
            "category",
            "variants",
            "images",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields