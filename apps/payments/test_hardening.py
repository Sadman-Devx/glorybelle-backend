"""Webhook hardening: lost-payment, duplicate delivery, out-of-order and broker failures."""
from unittest.mock import patch

import pytest

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.payments import services as payment_services
from apps.payments.models import Payment, ProcessedWebhookEvent

pytestmark = pytest.mark.django_db

SHIP = {"first_name": "A", "last_name": "B", "line1": "Via 1", "city": "Roma",
        "province": "RM", "postal_code": "00100", "country": "IT"}


def _event(evt_id, pi, kind="payment_intent.succeeded"):
    return {"id": evt_id, "type": kind, "data": {"object": {"id": pi}}}


@pytest.fixture
def variant(db):
    cat = Category.objects.create(name="C", slug="c-hard")
    prod = Product.objects.create(category=cat, name="P", slug="p-hard", base_price="100.00", metal="gold")
    return ProductVariant.objects.create(product=prod, metal="gold", size="1", sku="HARD-1", stock_quantity=10)


@pytest.fixture
def order(user, variant):
    cart = Cart.objects.create(user=user)
    cart_services.add_to_cart(cart, variant.id, quantity=2)
    return order_services.create_order_from_cart(
        cart=cart, email=user.email, shipping_address_data=SHIP, user=user
    )


def _payment(order, pi="pi_hard_1"):
    return Payment.objects.create(order=order, stripe_payment_intent_id=pi, amount=order.total,
                                  currency="EUR", status="pending", idempotency_key="k-" + pi)


def test_unknown_payment_intent_event_is_not_marked_processed(order):
    ok = payment_services.handle_payment_succeeded(_event("evt_a", "pi_late"))
    assert ok is False
    assert not ProcessedWebhookEvent.objects.filter(stripe_event_id="evt_a").exists()
    # Stripe retries the SAME event once the Payment row exists -> must now be processed
    _payment(order, "pi_late")
    assert payment_services.handle_payment_succeeded(_event("evt_a", "pi_late")) is True
    order.refresh_from_db()
    assert order.status == "paid"


def test_unknown_payment_intent_failure_event_not_marked_processed(order):
    assert payment_services.handle_payment_failed(_event("evt_f", "pi_nope", "payment_intent.payment_failed")) is False
    assert not ProcessedWebhookEvent.objects.filter(stripe_event_id="evt_f").exists()


@patch("apps.invoicing.tasks.generate_invoice.delay")
@patch("apps.invoicing.tasks.send_order_confirmation_email.delay")
def test_same_payment_intent_new_event_id_does_not_double_deduct(_mail, _inv, order, variant):
    _payment(order)
    payment_services.handle_payment_succeeded(_event("evt_1", "pi_hard_1"))
    variant.refresh_from_db()
    after_first = variant.stock_quantity
    assert after_first == 8
    assert payment_services.handle_payment_succeeded(_event("evt_2", "pi_hard_1")) is True
    variant.refresh_from_db()
    assert variant.stock_quantity == after_first
    _mail.assert_called_once()  # confirmation email not sent twice either


@patch("apps.invoicing.tasks.generate_invoice.delay")
@patch("apps.invoicing.tasks.send_order_confirmation_email.delay")
def test_late_failure_event_cannot_cancel_a_paid_order(_mail, _inv, order):
    _payment(order)
    payment_services.handle_payment_succeeded(_event("evt_ok", "pi_hard_1"))
    assert payment_services.handle_payment_failed(_event("evt_bad", "pi_hard_1", "payment_intent.payment_failed")) is True
    order.refresh_from_db()
    assert order.status == "paid"
    assert Payment.objects.get(stripe_payment_intent_id="pi_hard_1").status == "succeeded"


def test_broker_outage_does_not_turn_paid_order_into_error(order):
    _payment(order)
    boom = ConnectionError("redis down")
    with patch("apps.invoicing.tasks.send_order_confirmation_email.delay", side_effect=boom), \
         patch("apps.invoicing.tasks.generate_invoice.delay", side_effect=boom):
        assert payment_services.handle_payment_succeeded(_event("evt_b", "pi_hard_1")) is True
    order.refresh_from_db()
    assert order.status == "paid"
