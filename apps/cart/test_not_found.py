"""Stale / foreign cart ids must be 404, never a 500 (DoesNotExist leaking out)."""
import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductVariant

pytestmark = pytest.mark.django_db


@pytest.fixture
def variant(db):
    cat = Category.objects.create(name="C", slug="c-nf")
    prod = Product.objects.create(category=cat, name="P", slug="p-nf", base_price="10.00", metal="gold")
    return ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="NF-1", stock_quantity=9)


def test_add_unknown_variant_is_404():
    r = APIClient().post("/api/cart/items/", {"variant_id": 99999999, "quantity": 1}, format="json")
    assert r.status_code == 404


def test_add_inactive_variant_is_404(variant):
    ProductVariant.objects.filter(pk=variant.pk).update(is_active=False)
    r = APIClient().post("/api/cart/items/", {"variant_id": variant.pk, "quantity": 1}, format="json")
    assert r.status_code == 404


def test_patch_unknown_item_is_404(variant):
    c = APIClient()
    c.post("/api/cart/items/", {"variant_id": variant.pk, "quantity": 1}, format="json")
    assert c.patch("/api/cart/items/99999999/", {"quantity": 2}, format="json").status_code == 404


def test_patch_another_guests_item_is_404_and_untouched(variant):
    owner, other = APIClient(), APIClient()
    item_id = owner.post("/api/cart/items/", {"variant_id": variant.pk, "quantity": 1}, format="json").data["items"][0]["id"]
    assert other.patch(f"/api/cart/items/{item_id}/", {"quantity": 5}, format="json").status_code == 404
    assert owner.get("/api/cart/").data["items"][0]["quantity"] == 1
