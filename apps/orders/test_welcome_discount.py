"""
Welcome discount rule: 10% off ONE product (one unit of the most expensive item),
automatic, valid at any time after registering until the first order is paid.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as svc
from apps.orders.models import Order

pytestmark = pytest.mark.django_db
D = Decimal
SHIP = {"first_name": "A", "last_name": "B", "line1": "Via 1", "city": "Roma",
        "province": "RM", "postal_code": "00100", "country": "IT"}


def _variant(name, price, sku, stock=50):
    cat, _ = Category.objects.get_or_create(slug="c-wd", defaults={"name": "C"})
    prod = Product.objects.create(category=cat, name=name, slug=f"p-{sku.lower()}", base_price=price, metal="gold")
    return ProductVariant.objects.create(product=prod, metal="gold", size="1", sku=sku, stock_quantity=stock)


def _lines(*triples):
    return [(n, D(p), q) for n, p, q in triples]


# ------------------------------------------------------------------ the pure rule
def test_ten_percent_of_one_unit_of_the_most_expensive_item(user):
    r = svc.compute_first_purchase_discount(_lines(("Anello", "149.00", 2), ("Collana", "99.00", 1)), user)
    assert (r.percent, r.amount, r.product_name, r.unit_price) == (D("10.00"), D("14.90"), "Anello", D("149.00"))


def test_it_is_never_a_discount_on_the_whole_basket(user):
    r = svc.compute_first_purchase_discount(_lines(("Anello", "100.00", 5)), user)   # 5 units, 500 total
    assert r.amount == D("10.00")                                                   # NOT 50.00


def test_ties_go_to_the_first_item(user):
    r = svc.compute_first_purchase_discount(_lines(("Primo", "80.00", 1), ("Secondo", "80.00", 3)), user)
    assert r.product_name == "Primo" and r.amount == D("8.00")


@pytest.mark.parametrize("price,expected", [("33.33", "3.33"), ("33.35", "3.34"), ("0.04", "0.00"), ("0.05", "0.01")])
def test_rounding_is_half_up_to_the_cent(user, price, expected):
    r = svc.compute_first_purchase_discount(_lines(("X", price, 1)), user)
    assert r.amount == D(expected)
    assert r.applies is (D(expected) > 0)


def test_no_discount_for_guests_or_empty_carts_or_free_items(user):
    from django.contrib.auth.models import AnonymousUser

    assert not svc.compute_first_purchase_discount(_lines(("A", "50", 1)), AnonymousUser()).applies
    assert not svc.compute_first_purchase_discount(_lines(("A", "50", 1)), None).applies
    assert not svc.compute_first_purchase_discount([], user).applies
    assert not svc.compute_first_purchase_discount(_lines(("A", "50", 0)), user).applies
    assert not svc.compute_first_purchase_discount(_lines(("A", "0.00", 1)), user).applies


@override_settings(FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL=D("500.00"))
def test_optional_minimum_basket_is_still_respected(user):
    assert not svc.compute_first_purchase_discount(_lines(("A", "100", 2)), user).applies
    assert svc.compute_first_purchase_discount(_lines(("A", "300", 2)), user).applies


@override_settings(FIRST_PURCHASE_DISCOUNT_PERCENT=D("15.00"))
def test_percentage_comes_from_settings(user):
    assert svc.compute_first_purchase_discount(_lines(("A", "200", 1)), user).amount == D("30.00")


# ------------------------------------------------- "even if they buy a month after registering"
@pytest.mark.parametrize("days", [0, 1, 29, 31, 40, 365, 1000])
def test_discount_does_not_expire_with_time_since_registration(user, days):
    User.objects.filter(pk=user.pk).update(date_joined=timezone.now() - timedelta(days=days))
    user.refresh_from_db()
    assert svc.compute_first_purchase_discount(_lines(("A", "120", 1)), user).amount == D("12.00")


def _order(user, status):
    return Order.objects.create(
        order_number=f"GB-{status}-{Order.objects.count()}", user=user, email=user.email, status=status,
        shipping_first_name="A", shipping_last_name="B", shipping_line1="x", shipping_city="x",
        shipping_province="MI", shipping_postal_code="1", billing_first_name="A", billing_last_name="B",
        billing_line1="x", billing_city="x", billing_province="MI", billing_postal_code="1",
        subtotal="10.00", total="10.00")


@pytest.mark.parametrize("status", ["paid", "processing", "shipped", "delivered"])
def test_a_completed_order_uses_the_discount_up(user, status):
    _order(user, status)
    assert not svc.compute_first_purchase_discount(_lines(("A", "100", 1)), user).applies


@pytest.mark.parametrize("status", ["pending", "cancelled", "refunded"])
def test_unfinished_orders_do_not_use_it_up(user, status):
    _order(user, status)
    assert svc.compute_first_purchase_discount(_lines(("A", "100", 1)), user).applies


# ----------------------------------------------- the cart preview == what is charged
def _api(user=None):
    c = APIClient()
    if user:
        c.force_authenticate(user=user)
    return c


def test_cart_shows_the_discount_automatically_and_checkout_charges_exactly_that(user):
    a, b = _variant("Anello", "149.00", "WD-A"), _variant("Collana", "99.00", "WD-B")
    c = _api(user)
    c.post("/api/cart/items/", {"variant_id": a.pk, "quantity": 2}, format="json")
    r = c.post("/api/cart/items/", {"variant_id": b.pk, "quantity": 1}, format="json")

    assert r.data["total"] == "397.00"
    assert r.data["discount"] == {"percent": "10.00", "amount": "14.90", "product_name": "Anello", "unit_price": "149.00"}
    assert r.data["total_after_discount"] == "382.10"
    assert c.get("/api/cart/").data["discount"]["amount"] == "14.90"          # also on a plain GET

    cart = Cart.objects.get(user=user)
    order = svc.create_order_from_cart(cart=cart, email=user.email, shipping_address_data=SHIP, user=user)
    assert order.discount_amount == D("14.90")
    assert str(order.total) == r.data["total_after_discount"]                 # what the cart showed == what is charged
    assert order.discount_product_name == "Anello"
    detail = c.get(f"/api/orders/{order.order_number}/")
    assert detail.data["discount_product_name"] == "Anello" and detail.data["has_discount"] is True


def test_guest_cart_has_no_discount_but_the_field_is_present(variant_factory=None):
    v = _variant("Anello", "149.00", "WD-G")
    c = _api()
    r = c.post("/api/cart/items/", {"variant_id": v.pk, "quantity": 1}, format="json")
    assert r.data["discount"] is None
    assert r.data["total_after_discount"] == r.data["total"] == "149.00"


def test_cart_stops_showing_the_discount_after_the_first_paid_order(user):
    v = _variant("Anello", "149.00", "WD-P")
    c = _api(user)
    assert c.post("/api/cart/items/", {"variant_id": v.pk, "quantity": 1}, format="json").data["discount"]
    _order(user, "paid")
    r = c.get("/api/cart/")
    assert r.data["discount"] is None and r.data["total_after_discount"] == r.data["total"]


def test_empty_cart_has_no_discount(user):
    r = _api(user).get("/api/cart/")
    assert r.data["discount"] is None and r.data["total_after_discount"] == "0.00"


def test_registration_message_describes_the_one_product_rule(api_client, user):
    guest = api_client.get("/api/accounts/first-purchase-discount/").data["message"]
    assert "un prodotto" in guest
    c = _api(user)
    signed = c.get("/api/accounts/first-purchase-discount/").data
    assert signed["eligible"] is True and "un prodotto" in signed["message"] and "automaticamente" in signed["message"]


def test_stripe_amount_is_the_discounted_total(user):
    """The PaymentIntent must be created for total (after discount), in cents."""
    v = _variant("Anello", "149.00", "WD-S")
    c = _api(user)
    c.post("/api/cart/items/", {"variant_id": v.pk, "quantity": 2}, format="json")      # 298.00 -> -14.90
    with patch("apps.orders.views.create_payment_intent", return_value=("cs", "pi_wd")) as pi:
        r = c.post("/api/checkout/", {"email": user.email, "shipping_address": SHIP}, format="json")
    assert r.status_code == 201, r.data
    order = pi.call_args.args[0]
    assert order.total == D("283.10") and int(order.total * 100) == 28310
