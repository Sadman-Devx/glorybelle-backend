"""
GLORYBELLE — Catalog Signals.

Cache invalidation on Product/Category save/delete.
Per rule.md: signals are acceptable for side effects like cache invalidation,
but NOT for core transactional logic.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.cache import invalidate_category_cache, invalidate_product_cache

from .models import Category, Product, ProductVariant


@receiver([post_save, post_delete], sender=Product)
def invalidate_product_on_change(sender, instance, **kwargs):
    """Clear product cache when any product is created/updated/deleted."""
    invalidate_product_cache()


@receiver([post_save, post_delete], sender=ProductVariant)
def invalidate_product_on_variant_change(sender, instance, **kwargs):
    """Clear product cache when any variant changes (stock, price, etc.)."""
    invalidate_product_cache()


@receiver([post_save, post_delete], sender=Category)
def invalidate_category_on_change(sender, instance, **kwargs):
    """Clear category cache when any category is created/updated/deleted."""
    invalidate_category_cache()
    # Also invalidate products since they include category data
    invalidate_product_cache()
