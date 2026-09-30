"""
GLORYBELLE — Redis Cache Utilities.

Helpers for cache key management and invalidation.
Per architecture.md: Redis is used for HTTP response cache with 5-min TTL.
"""
import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Cache key prefixes
PRODUCT_LIST_PREFIX = "product_list"
PRODUCT_DETAIL_PREFIX = "product_detail"
CATEGORY_LIST_PREFIX = "category_list"
CATEGORY_DETAIL_PREFIX = "category_detail"

# Default TTL in seconds
DEFAULT_TTL = 300  # 5 minutes


def make_cache_key(prefix: str, **kwargs) -> str:
    """
    Generate a deterministic cache key from a prefix and keyword arguments.

    Example:
        make_cache_key("product_list", category="anelli", metal="argento", page=1)
        → "glorybelle:product_list:a1b2c3d4"
    """
    raw = "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
    suffix = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{prefix}:{suffix}"


def get_cached(key: str):
    """Get a value from cache, returns None on miss."""
    return cache.get(key)


def set_cached(key: str, value, ttl: int = DEFAULT_TTL):
    """Set a value in cache with the given TTL."""
    cache.set(key, value, ttl)


def _safe_delete_pattern(pattern):
    """
    Delete cache keys matching a pattern.

    Falls back to cache.clear() on backends that don't support
    pattern-based deletion (e.g., LocMemCache in tests).
    """
    try:
        cache.delete_pattern(pattern)
    except (AttributeError, NotImplementedError):
        # Non-Redis backend — clear entire cache as fallback
        cache.clear()
    except Exception:
        # Redis not available (ConnectionError, etc.) — silently skip
        pass


def invalidate_product_cache():
    """
    Invalidate all product-related cache keys.

    Called from catalog/signals.py on Product/ProductVariant save/delete.
    Uses key pattern deletion — clears all keys with the product prefix.
    """
    logger.info("Invalidating product cache")
    _safe_delete_pattern(f"*{PRODUCT_LIST_PREFIX}*")
    _safe_delete_pattern(f"*{PRODUCT_DETAIL_PREFIX}*")


def invalidate_category_cache():
    """
    Invalidate all category-related cache keys.

    Called from catalog/signals.py on Category save/delete.
    """
    logger.info("Invalidating category cache")
    _safe_delete_pattern(f"*{CATEGORY_LIST_PREFIX}*")
    _safe_delete_pattern(f"*{CATEGORY_DETAIL_PREFIX}*")


def invalidate_all():
    """Nuclear option — clear the entire cache."""
    logger.warning("Invalidating ALL cache")
    cache.clear()

