"""Checkout retries and concurrent submissions must not create payable duplicates."""
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
from unittest.mock import patch

import pytest
from django.db import close_old_connections, connections
from rest_framework.test import APIClient

from apps.cart.models import Cart, StockReservation
from apps.cart.services import update_cart_item_quantity
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders.models import Order
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db(transaction=True)

CHECKOUT_URL = "/api/checkout/"
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
    category = Category.objects.create(name="Checkout", slug="checkout-idem")
    product = Product.objects.create(
        category=category,
        name="Checkout Test Product",
        slug=f"checkout-idem-{uuid.uuid4().hex[:8]}",
        base_price="100.00",
        metal="gold",
    )
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="1",
        sku=f"CHECKOUT-{uuid.uuid4().hex[:8]}",
        stock_quantity=20,
    )


def _create_guest_cart(variant):
    token = uuid.uuid4().hex
    response = APIClient().post(
        "/api/cart/items/",
        {"variant_id": variant.pk, "quantity": 1},
        format="json",
        HTTP_X_CART_TOKEN=token,
    )
    assert response.status_code == 201, response.data
    cart = Cart.objects.get(session_key=f"gt_{token}")
    return token, cart


def _payload(key=None, **changes):
    data = {
        "email": "checkout@example.com",
        "shipping_address": SHIPPING,
    }
    if key is not None:
        data["idempotency_key"] = str(key)
    data.update(changes)
    return data


def _fake_create_payment_intent(order):
    payment_intent_id = f"pi_checkout_test_{order.pk}"
    Payment.objects.get_or_create(
        stripe_payment_intent_id=payment_intent_id,
        defaults={
            "order": order,
            "amount": order.total,
            "currency": "EUR",
            "status": "pending",
            "idempotency_key": f"checkout_test_{order.pk}",
        },
    )
    return f"{payment_intent_id}_secret_test", payment_intent_id


@pytest.mark.parametrize("request_count", [2, 10])
def test_parallel_checkout_posts_create_one_order_and_payment_intent(
    variant, request_count
):
    token, cart = _create_guest_cart(variant)
    barrier = threading.Barrier(request_count)

    def submit_checkout(_):
        close_old_connections()
        try:
            client = APIClient()
            barrier.wait(timeout=20)
            response = client.post(
                CHECKOUT_URL,
                _payload(uuid.uuid4()),
                format="json",
                HTTP_X_CART_TOKEN=token,
            )
            return response.status_code, response.data
        finally:
            connections.close_all()

    with patch(
        "apps.orders.views.create_payment_intent",
        side_effect=_fake_create_payment_intent,
    ) as create_intent:
        with ThreadPoolExecutor(max_workers=request_count) as executor:
            responses = list(executor.map(submit_checkout, range(request_count)))

    assert sorted(status_code for status_code, _ in responses) == [
        200,
    ] * (request_count - 1) + [201]
    assert all(data["order"]["order_number"] == responses[0][1]["order"]["order_number"]
               for _, data in responses)
    assert sum(bool(data.get("idempotent_replay")) for _, data in responses) == request_count - 1
    assert Order.objects.filter(cart=cart).count() == 1
    assert Payment.objects.filter(order__cart=cart).count() == 1
    assert len({data["payment_intent_id"] for _, data in responses}) == 1


def test_same_idempotency_key_replays_and_keeps_stock_reservations(variant):
    token, cart = _create_guest_cart(variant)
    reservation_count = StockReservation.objects.filter(
        cart_item__cart=cart, is_active=True
    ).count()
    variant.refresh_from_db()
    reserved_quantity = variant.reserved_quantity
    key = uuid.uuid4()

    with patch(
        "apps.orders.views.create_payment_intent",
        side_effect=_fake_create_payment_intent,
    ) as create_intent:
        client = APIClient()
        first = client.post(
            CHECKOUT_URL,
            _payload(key),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )
        replay = APIClient().post(
            CHECKOUT_URL,
            _payload(key),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.data["idempotent_replay"] is True
    assert replay.data["order"]["id"] == first.data["order"]["id"]
    assert replay.data["payment_intent_id"] == first.data["payment_intent_id"]
    assert Payment.objects.filter(order__cart=cart).count() == 1
    variant.refresh_from_db()
    assert variant.reserved_quantity == reserved_quantity
    assert StockReservation.objects.filter(
        cart_item__cart=cart, is_active=True
    ).count() == reservation_count


def test_changed_cart_cancels_old_intent_before_creating_new_order(variant):
    token, cart = _create_guest_cart(variant)
    create_intent = patch(
        "apps.orders.views.create_payment_intent",
        side_effect=_fake_create_payment_intent,
    )
    cancel_intent = patch("apps.payments.stripe_client.cancel_payment_intent")
    with create_intent, cancel_intent as cancel:
        first = APIClient().post(
            CHECKOUT_URL,
            _payload(uuid.uuid4()),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )
        old_order = Order.objects.get(pk=first.data["order"]["id"])
        item = cart.items.get()
        update_cart_item_quantity(cart, item.pk, 2)
        reservations_before = StockReservation.objects.filter(
            cart_item__cart=cart, is_active=True
        ).count()
        variant.refresh_from_db()
        reserved_before = variant.reserved_quantity

        second = APIClient().post(
            CHECKOUT_URL,
            _payload(uuid.uuid4()),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    old_order.refresh_from_db()
    assert old_order.status == "cancelled"
    old_payment = Payment.objects.get(order=old_order)
    assert old_payment.status == "failed"
    cancel.assert_called_once_with(old_payment.stripe_payment_intent_id)
    assert Payment.objects.filter(order__cart=cart, status="pending").count() == 1
    assert Order.objects.filter(cart=cart, status="pending").count() == 1
    variant.refresh_from_db()
    assert variant.reserved_quantity == reserved_before
    assert StockReservation.objects.filter(
        cart_item__cart=cart, is_active=True
    ).count() == reservations_before


def test_new_key_with_same_discounted_cart_replays_without_releasing_discount(
    user, variant
):
    client = APIClient()
    client.force_authenticate(user=user)
    added = client.post(
        "/api/cart/items/",
        {"variant_id": variant.pk, "quantity": 1},
        format="json",
    )
    assert added.status_code == 201
    cart = Cart.objects.get(user=user)
    payload = _payload(uuid.uuid4(), email=user.email)

    with patch(
        "apps.orders.views.create_payment_intent",
        side_effect=_fake_create_payment_intent,
    ) as create_intent, patch(
        "apps.payments.stripe_client.cancel_payment_intent"
    ) as cancel_intent:
        first = client.post(CHECKOUT_URL, payload, format="json")
        payload["idempotency_key"] = str(uuid.uuid4())
        replay = client.post(CHECKOUT_URL, payload, format="json")

    assert first.status_code == 201
    assert first.data["order"]["discount_amount"] == "10.00"
    assert replay.status_code == 200
    assert replay.data["idempotent_replay"] is True
    assert replay.data["order"]["id"] == first.data["order"]["id"]
    assert Order.objects.filter(cart=cart, status="pending").count() == 1
    assert Order.objects.filter(
        cart=cart, status="pending", discount_amount__gt=0
    ).count() == 1
    assert Payment.objects.filter(order__cart=cart).count() == 1
    cancel_intent.assert_not_called()


def test_same_idempotency_key_cannot_be_reused_for_changed_checkout(variant):
    token, cart = _create_guest_cart(variant)
    key = uuid.uuid4()
    with patch(
        "apps.orders.views.create_payment_intent",
        side_effect=_fake_create_payment_intent,
    ) as create_intent:
        first = APIClient().post(
            CHECKOUT_URL,
            _payload(key),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )
        changed = APIClient().post(
            CHECKOUT_URL,
            _payload(key, email="different@example.com"),
            format="json",
            HTTP_X_CART_TOKEN=token,
        )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert create_intent.call_count == 1
    assert Order.objects.filter(cart=cart).count() == 1
