"""Pending-order expiry must preserve payments and release only owned stock."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import threading
from unittest.mock import patch
import uuid

import pytest
from django.db import close_old_connections, connections
from django.utils import timezone

from apps.cart import services as cart_services
from apps.cart.models import Cart, StockReservation
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.orders.tasks import cancel_expired_pending_orders
from apps.payments import services as payment_services
from apps.payments.models import Payment
from apps.payments.stripe_client import PaymentIntentNotCancellable

pytestmark = pytest.mark.django_db

SHIPPING = {
    "first_name": "A",
    "last_name": "B",
    "line1": "Via 1",
    "city": "Roma",
    "province": "RM",
    "postal_code": "00100",
    "country": "IT",
}


@pytest.fixture
def variant(db):
    category = Category.objects.create(
        name="Expiry", slug=f"expiry-{uuid.uuid4().hex[:8]}"
    )
    product = Product.objects.create(
        category=category,
        name="Expiry Test Product",
        slug=f"expiry-product-{uuid.uuid4().hex[:8]}",
        base_price="100.00",
        metal="gold",
    )
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="1",
        sku=f"EXPIRY-{uuid.uuid4().hex[:8]}",
        stock_quantity=10,
    )


def _make_order(variant, *, user=None, session=None, payment=True):
    cart = Cart.objects.create(user=user, session_key=session)
    cart_services.add_to_cart(cart, variant.pk, quantity=1)
    order = order_services.create_order_from_cart(
        cart=cart,
        email=user.email if user else "guest@example.com",
        shipping_address_data=SHIPPING,
        user=user,
    )
    payment_obj = None
    if payment:
        pi_id = f"pi_expiry_{order.pk}"
        payment_obj = Payment.objects.create(
            order=order,
            stripe_payment_intent_id=pi_id,
            amount=order.total,
            currency="EUR",
            status="pending",
            idempotency_key=f"expiry_key_{order.pk}",
        )
        order.stripe_payment_intent_id = pi_id
        order.save(update_fields=["stripe_payment_intent_id"])
    return order, payment_obj, cart


def _age_order(order, minutes=61):
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timedelta(minutes=minutes)
    )


def _succeeded_event(event_id, payment_intent_id):
    return {
        "id": event_id,
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": payment_intent_id}},
    }


def test_expiry_boundary_and_successful_cancellation(variant):
    order, payment, _ = _make_order(variant)
    fixed_now = timezone.now()
    Order.objects.filter(pk=order.pk).update(
        created_at=fixed_now - timedelta(minutes=60)
    )

    with patch("apps.orders.tasks.timezone.now", return_value=fixed_now), patch(
        "apps.orders.tasks.cancel_payment_intent"
    ) as cancel:
        assert cancel_expired_pending_orders.run() == 0
        order.refresh_from_db()
        assert order.status == "pending"

        Order.objects.filter(pk=order.pk).update(
            created_at=fixed_now - timedelta(minutes=60, seconds=1)
        )
        assert cancel_expired_pending_orders.run() == 1

    cancel.assert_called_once_with(payment.stripe_payment_intent_id)
    order.refresh_from_db()
    payment.refresh_from_db()
    variant.refresh_from_db()
    assert order.status == "cancelled"
    assert payment.status == "failed"
    assert variant.reserved_quantity == 0
    assert not StockReservation.objects.filter(
        order=order, is_active=True
    ).exists()

    with patch("apps.orders.tasks.cancel_payment_intent") as cancel_again:
        assert cancel_expired_pending_orders.run() == 0
    cancel_again.assert_not_called()


@pytest.mark.parametrize("stripe_state", ["succeeded", "processing"])
def test_stripe_non_cancellable_intent_leaves_order_payment_and_reservation(
    variant, stripe_state
):
    order, payment, _ = _make_order(variant)
    _age_order(order)
    with patch(
        "apps.orders.tasks.cancel_payment_intent",
        side_effect=PaymentIntentNotCancellable(stripe_state, retryable=False),
    ) as cancel:
        assert cancel_expired_pending_orders.run() == 0

    cancel.assert_called_once_with(payment.stripe_payment_intent_id)
    order.refresh_from_db()
    payment.refresh_from_db()
    variant.refresh_from_db()
    reservation = StockReservation.objects.get(order=order)
    assert order.status == "pending"
    assert payment.status == "pending"
    assert reservation.is_active
    assert variant.reserved_quantity == 1


def test_stripe_unavailable_leaves_order_untouched_and_retries(variant):
    order, payment, _ = _make_order(variant)
    _age_order(order)
    with patch(
        "apps.orders.tasks.cancel_payment_intent",
        side_effect=PaymentIntentNotCancellable("Stripe unavailable", retryable=True),
    ) as cancel:
        assert cancel_expired_pending_orders.run() == 0
        order.refresh_from_db()
        assert order.status == "pending"

    with patch("apps.orders.tasks.cancel_payment_intent") as retry:
        assert cancel_expired_pending_orders.run() == 1
    cancel.assert_called_once_with(payment.stripe_payment_intent_id)
    retry.assert_called_once_with(payment.stripe_payment_intent_id)


def test_expiry_releases_only_reservations_for_that_order(variant):
    expiring, _, _ = _make_order(variant, session="guest-expiring")
    other, _, _ = _make_order(variant, session="guest-other")
    _age_order(expiring)

    with patch("apps.orders.tasks.cancel_payment_intent"):
        assert cancel_expired_pending_orders.run() == 1

    expiring.refresh_from_db()
    other.refresh_from_db()
    variant.refresh_from_db()
    assert expiring.status == "cancelled"
    assert other.status == "pending"
    assert not StockReservation.objects.filter(
        order=expiring, is_active=True
    ).exists()
    assert StockReservation.objects.filter(order=other, is_active=True).exists()
    assert variant.reserved_quantity == 1


def test_expired_discount_hold_can_be_used_by_next_checkout(user, variant):
    order, payment, cart = _make_order(variant, user=user)
    assert order.discount_amount > 0
    _age_order(order)

    with patch("apps.orders.tasks.cancel_payment_intent"):
        assert cancel_expired_pending_orders.run() == 1

    cart_services.add_to_cart(cart, variant.pk, quantity=1)
    replacement = order_services.create_order_from_cart(
        cart=cart,
        email=user.email,
        shipping_address_data=SHIPPING,
        user=user,
    )
    order.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == "cancelled"
    assert payment.status == "failed"
    assert replacement.discount_amount > 0


@pytest.mark.parametrize("webhook_first", [True, False])
@patch("apps.invoicing.tasks.send_order_confirmation_email.delay")
@patch("apps.invoicing.tasks.generate_invoice.delay")
def test_webhook_and_expiry_race_preserves_a_successful_payment(
    _invoice, _email, variant, webhook_first
):
    order, payment, _ = _make_order(variant)
    _age_order(order)
    event = _succeeded_event(f"evt_race_{webhook_first}", payment.stripe_payment_intent_id)

    if webhook_first:
        assert payment_services.handle_payment_succeeded(event) is True
        with patch("apps.orders.tasks.cancel_payment_intent") as cancel:
            assert cancel_expired_pending_orders.run() == 0
        cancel.assert_not_called()
    else:
        with patch(
            "apps.orders.tasks.cancel_payment_intent",
            side_effect=PaymentIntentNotCancellable("intent succeeded", retryable=False),
        ):
            assert cancel_expired_pending_orders.run() == 0
        assert payment_services.handle_payment_succeeded(event) is True

    order.refresh_from_db()
    payment.refresh_from_db()
    variant.refresh_from_db()
    assert order.status == "paid"
    assert payment.status == "succeeded"
    assert variant.stock_quantity == 9
    assert variant.reserved_quantity == 0


def test_paid_orders_are_never_sent_to_stripe(variant):
    order, payment, _ = _make_order(variant)
    order.status = "paid"
    order.save(update_fields=["status"])
    payment.status = "succeeded"
    payment.save(update_fields=["status"])
    _age_order(order)

    with patch("apps.orders.tasks.cancel_payment_intent") as cancel:
        assert cancel_expired_pending_orders.run() == 0
    cancel.assert_not_called()


@pytest.mark.django_db(transaction=True)
@patch("apps.invoicing.tasks.send_order_confirmation_email.delay")
@patch("apps.invoicing.tasks.generate_invoice.delay")
def test_concurrent_webhook_waits_for_stripe_cancel_decision(
    _invoice, _email, variant
):
    order, payment, _ = _make_order(variant)
    _age_order(order)
    cancel_started = threading.Event()
    webhook_started = threading.Event()

    def cancel_intent(_payment_intent_id):
        cancel_started.set()
        assert webhook_started.wait(timeout=10)
        raise PaymentIntentNotCancellable(
            "Stripe reports the intent is already completing", retryable=False
        )

    def expire():
        close_old_connections()
        try:
            with patch(
                "apps.orders.tasks.cancel_payment_intent",
                side_effect=cancel_intent,
            ):
                return cancel_expired_pending_orders.run()
        finally:
            connections.close_all()

    def process_webhook():
        close_old_connections()
        try:
            assert cancel_started.wait(timeout=10)
            webhook_started.set()
            return payment_services.handle_payment_succeeded(
                _succeeded_event("evt_expiry_concurrent", payment.stripe_payment_intent_id)
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        expiry_result = executor.submit(expire)
        webhook_result = executor.submit(process_webhook)
        assert expiry_result.result(timeout=20) == 0
        assert webhook_result.result(timeout=20) is True

    order.refresh_from_db()
    payment.refresh_from_db()
    variant.refresh_from_db()
    assert order.status == "paid"
    assert payment.status == "succeeded"
    assert variant.stock_quantity == 9
    assert variant.reserved_quantity == 0
