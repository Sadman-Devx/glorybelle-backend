"""Bad checkout input must be a 4xx, never a 500."""
import pytest
from rest_framework.test import APIClient

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant

pytestmark = pytest.mark.django_db
SHIP = {"first_name": "A", "last_name": "B", "line1": "Via 1", "city": "Roma",
        "province": "RM", "postal_code": "00100", "country": "IT"}


@pytest.fixture
def guest(db):
    cat = Category.objects.create(name="C", slug="c-val")
    prod = Product.objects.create(category=cat, name="P", slug="p-val", base_price="10.00", metal="gold")
    var = ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="VAL-1", stock_quantity=5)
    c = APIClient()
    assert c.post("/api/cart/items/", {"variant_id": var.pk, "quantity": 1}, format="json").status_code == 201
    return c


def post(c, **extra):
    body = {"email": "a@example.com", "shipping_address": SHIP}
    body.update(extra)
    return c.post("/api/checkout/", body, format="json")


def test_guest_sending_only_shipping_address_id_is_400(guest):
    r = guest.post("/api/checkout/", {"email": "a@example.com", "shipping_address_id": 1}, format="json")
    assert r.status_code == 400


def test_unknown_saved_address_is_400(user, guest):
    guest.force_authenticate(user=user)
    guest.post("/api/cart/merge/", {}, format="json")
    r = guest.post("/api/checkout/", {"email": user.email, "shipping_address_id": 99999}, format="json")
    assert r.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("line1", "X" * 600), ("city", "X" * 101), ("province", "X" * 11),
    ("postal_code", "9" * 11), ("country", "ITA"), ("first_name", ["a"]), ("line1", {"a": 1}),
])
def test_oversized_or_wrong_type_address_field_is_400(guest, field, value):
    assert post(guest, shipping_address=dict(SHIP, **{field: value})).status_code == 400


def test_missing_required_address_field_is_400(guest):
    assert post(guest, shipping_address=dict(SHIP, city="")).status_code == 400


def test_billing_address_missing_keys_is_400_not_keyerror(guest):
    r = post(guest, billing_same_as_shipping=False, billing_address={"first_name": "x"})
    assert r.status_code == 400


def test_billing_required_when_not_same_as_shipping(guest):
    assert post(guest, billing_same_as_shipping=False).status_code == 400


# ---- Stripe outage at PaymentIntent creation must be a clean 503, not an HTML 500
def test_stripe_outage_during_checkout_is_a_clean_503(guest):
    import stripe
    from unittest.mock import patch

    with patch.object(stripe.PaymentIntent, "create", side_effect=stripe.error.APIConnectionError("down")):
        r = post(guest)
    assert r.status_code == 503
    assert r["Content-Type"].startswith("application/json")
    assert r.data["error"]["code"] == "payment_unavailable"
