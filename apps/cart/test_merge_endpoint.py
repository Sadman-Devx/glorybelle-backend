"""POST /api/cart/merge/ — guest cart is identified by the session cookie."""
import pytest
from rest_framework.test import APIClient

from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant

pytestmark = pytest.mark.django_db
URL = "/api/cart/merge/"


@pytest.fixture
def variant(db):
    cat = Category.objects.create(name="C", slug="c-merge")
    prod = Product.objects.create(category=cat, name="P", slug="p-merge", base_price="10.00", metal="gold")
    return ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="MRG-1", stock_quantity=9)


def test_anonymous_merge_is_401_not_500(api_client):
    assert api_client.post(URL, {}, format="json").status_code == 401


def test_guest_cart_merged_via_session_cookie(user, variant):
    c = APIClient()
    r = c.post("/api/cart/items/", {"variant_id": variant.pk, "quantity": 2}, format="json")
    assert r.status_code == 201
    c.force_authenticate(user=user)  # same client keeps the session cookie
    r = c.post(URL, {}, format="json")
    assert r.status_code == 200
    assert r.data["item_count"] == 2
    assert Cart.objects.filter(user=user).count() == 1
    assert not Cart.objects.filter(user__isnull=True, session_key__isnull=False).exists()


def test_body_session_key_is_ignored(user, variant, create_user):
    victim = Cart.objects.create(session_key="victim-session-key")
    victim.items.create(variant=variant, quantity=3)
    c = APIClient()
    c.force_authenticate(user=user)
    r = c.post(URL, {"session_key": "victim-session-key"}, format="json")
    assert r.status_code == 200
    assert r.data["item_count"] == 0  # someone else's cart must NOT be pulled in
    assert Cart.objects.filter(session_key="victim-session-key").exists()
