"""First-purchase discount: at most ONE open discounted order per user."""
from unittest.mock import patch

import pytest

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.stripe_client import PaymentIntentNotCancellable

pytestmark = pytest.mark.django_db
CANCEL = "apps.payments.stripe_client.cancel_payment_intent"
SHIP = {"first_name": "A", "last_name": "B", "line1": "Via 1", "city": "Roma",
        "province": "RM", "postal_code": "00100", "country": "IT"}


@pytest.fixture
def cart(user, db):
    cat = Category.objects.create(name="C", slug="c-disc")
    prod = Product.objects.create(category=cat, name="P", slug="p-disc", base_price="100.00", metal="gold")
    var = ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="DISC-1", stock_quantity=10)
    c = Cart.objects.create(user=user)
    cart_services.add_to_cart(c, var.id, quantity=1)
    return c


def _checkout(cart, user):
    return order_services.create_order_from_cart(
        cart=cart, email=user.email, shipping_address_data=SHIP, user=user
    )


def _pay(order, pi):
    Payment.objects.create(order=order, stripe_payment_intent_id=pi, amount=order.total,
                           currency="EUR", status="pending", idempotency_key="k-" + pi)


def test_second_checkout_supersedes_first_and_cancels_its_payment_intent(user, cart):
    first = _checkout(cart, user)
    assert first.discount_amount > 0
    _pay(first, "pi_one")
    with patch(CANCEL) as cancel:
        second = _checkout(cart, user)
    cancel.assert_called_once_with("pi_one")
    first.refresh_from_db()
    assert first.status == "cancelled"
    assert Payment.objects.get(order=first).status == "failed"
    assert second.discount_amount > 0
    open_discounted = Order.objects.filter(user=user, status="pending", discount_amount__gt=0)
    assert list(open_discounted) == [second]


def test_no_discount_when_earlier_payment_intent_cannot_be_cancelled(user, cart):
    first = _checkout(cart, user)
    _pay(first, "pi_paying")
    with patch(CANCEL, side_effect=PaymentIntentNotCancellable("already succeeded", retryable=False)):
        second = _checkout(cart, user)
    first.refresh_from_db()
    assert first.status == "pending"          # untouched: it may still get paid
    assert second.discount_amount == 0        # so the new order must NOT be discounted too


def test_pending_order_without_payment_is_simply_superseded(user, cart):
    first = _checkout(cart, user)             # abandoned before a PaymentIntent existed
    with patch(CANCEL) as cancel:
        second = _checkout(cart, user)
    cancel.assert_not_called()
    first.refresh_from_db()
    assert first.status == "cancelled" and second.discount_amount > 0


def test_user_who_already_bought_is_untouched(user, cart):
    done = _checkout(cart, user)
    done.status = "paid"
    done.save(update_fields=["status"])
    with patch(CANCEL) as cancel:
        again = _checkout(cart, user)
    cancel.assert_not_called()
    assert again.discount_amount == 0


def test_guest_never_gets_a_discount(cart):
    guest_cart = Cart.objects.create(session_key="guest-disc")
    variant = cart.items.first().variant
    cart_services.add_to_cart(guest_cart, variant.id, quantity=1)
    order = order_services.create_order_from_cart(
        cart=guest_cart, email="g@example.com", shipping_address_data=SHIP, user=None
    )
    assert order.discount_amount == 0


def test_stripe_unreachable_asks_customer_to_retry_instead_of_dropping_the_discount(user, cart):
    from core.exceptions import PaymentServiceUnavailable

    first = _checkout(cart, user)
    _pay(first, "pi_unknown_state")
    with patch(CANCEL, side_effect=PaymentIntentNotCancellable("network", retryable=True)):
        with pytest.raises(PaymentServiceUnavailable):
            _checkout(cart, user)
    first.refresh_from_db()
    assert first.status == "pending"                      # nothing was changed
    assert Order.objects.filter(user=user).count() == 1   # and no second order was created
    assert Payment.objects.get(order=first).status == "pending"


def test_checkout_endpoint_returns_503_when_stripe_is_unreachable(user, cart):
    from rest_framework.test import APIClient

    first = _checkout(cart, user)
    _pay(first, "pi_unknown_state")
    client = APIClient()
    client.force_authenticate(user=user)
    with patch(CANCEL, side_effect=PaymentIntentNotCancellable("network", retryable=True)):
        r = client.post("/api/checkout/", {"email": user.email, "shipping_address": SHIP}, format="json")
    assert r.status_code == 503
    assert r.data["error"]["code"] == "payment_unavailable"
