"""?page_size must be part of the product-list cache key."""
import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product

pytestmark = pytest.mark.django_db


@pytest.fixture
def products(db):
    cat = Category.objects.create(name="C", slug="c-ps")
    for i in range(12):
        Product.objects.create(category=cat, name=f"P{i}", slug=f"p-ps-{i}", base_price="10.00", metal="gold")


def _n(c, qs):
    return len(c.get(f"/api/products/{qs}").data["results"])


def test_page_size_is_honoured_even_after_default_page_was_cached(products):
    c = APIClient()
    assert _n(c, "") == 8                 # warms the cache with the default page
    assert _n(c, "?page_size=3") == 3
    assert _n(c, "?page_size=100") == 12
    assert _n(c, "") == 8                 # default still correct


def test_filters_still_part_of_key(products):
    c = APIClient()
    assert _n(c, "?min_price=5") == 8
    assert _n(c, "?min_price=999") == 0
