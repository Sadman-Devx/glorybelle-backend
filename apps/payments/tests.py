"""
GLORYBELLE — Payment Tests.

Per roadmap Day 7:
  "Replaying the same webhook payload twice results in the order being
  marked paid exactly once, not double-processed."
"""
import pytest
from decimal import Decimal
from unittest.mock import patch

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.payments.models import Payment, ProcessedWebhookEvent
from apps.payments import services as payment_services


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-pay-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Payment Test Ring",
        slug="payment-test-ring",
        base_price="149.00",
        metal="gold",
    )


@pytest.fixture
def variant(product):
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="PAY-TEST-GOLD-52",
        stock_quantity=10,
    )


@pytest.fixture
def shipping_address_data():
    return {
        "first_name": "Francesca",
        "last_name": "Rossi",
        "line1": "Via Roma 42",
        "city": "Milano",
        "province": "MI",
        "postal_code": "20121",
        "country": "IT",
    }


@pytest.fixture
def order_with_payment(user, variant, shipping_address_data):
    """Create a complete order with a pending payment."""
    cart = Cart.objects.create(user=user)
    cart_services.add_to_cart(cart, variant.id, quantity=2)

    order = order_services.create_order_from_cart(
        cart=cart,
        email="test@glorybelle.it",
        shipping_address_data=shipping_address_data,
        user=user,
    )

    payment = Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_test_123456",
        amount=order.total,
        currency="EUR",
        status="pending",
        idempotency_key="test_key_123456",
    )
    order.stripe_payment_intent_id = "pi_test_123456"
    order.save(update_fields=["stripe_payment_intent_id"])

    return order, payment


def _make_succeeded_event(event_id, payment_intent_id):
    """Helper to create a mock payment_intent.succeeded event."""
    return {
        "id": event_id,
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": payment_intent_id,
                "charges": {
                    "data": [{"id": "ch_test_123"}],
                },
            },
        },
    }


def _make_failed_event(event_id, payment_intent_id):
    """Helper to create a mock payment_intent.payment_failed event."""
    return {
        "id": event_id,
        "type": "payment_intent.payment_failed",
        "data": {
            "object": {
                "id": payment_intent_id,
            },
        },
    }


@pytest.mark.django_db
class TestPaymentSucceeded:
    @patch("apps.invoicing.tasks.send_order_confirmation_email")
    @patch("apps.invoicing.tasks.generate_invoice")
    def test_payment_marks_order_paid(
        self, mock_invoice, mock_email, order_with_payment
    ):
        order, payment = order_with_payment
        event = _make_succeeded_event("evt_test_001", "pi_test_123456")

        result = payment_services.handle_payment_succeeded(event)

        assert result is True
        order.refresh_from_db()
        payment.refresh_from_db()
        assert order.status == "paid"
        assert payment.status == "succeeded"

    @patch("apps.invoicing.tasks.send_order_confirmation_email")
    @patch("apps.invoicing.tasks.generate_invoice")
    def test_payment_deducts_stock(
        self, mock_invoice, mock_email, order_with_payment, variant
    ):
        order, payment = order_with_payment
        initial_stock = variant.stock_quantity  # 10
        event = _make_succeeded_event("evt_test_002", "pi_test_123456")

        payment_services.handle_payment_succeeded(event)

        variant.refresh_from_db()
        assert variant.stock_quantity == initial_stock - 2  # ordered 2

    @patch("apps.invoicing.tasks.send_order_confirmation_email")
    @patch("apps.invoicing.tasks.generate_invoice")
    def test_idempotency_same_event_twice(
        self, mock_invoice, mock_email, order_with_payment
    ):
        """
        CRITICAL IDEMPOTENCY TEST.

        Per roadmap Day 7: "replaying the same webhook payload twice
        results in the order being marked paid exactly once."
        """
        order, payment = order_with_payment
        event = _make_succeeded_event("evt_test_003", "pi_test_123456")

        # First call
        result1 = payment_services.handle_payment_succeeded(event)
        assert result1 is True

        # Second call — same event ID
        result2 = payment_services.handle_payment_succeeded(event)
        assert result2 is True  # Returns True (already processed)

        # Only one ProcessedWebhookEvent should exist
        assert ProcessedWebhookEvent.objects.filter(
            stripe_event_id="evt_test_003"
        ).count() == 1

        # Order should still be 'paid', not double-processed
        order.refresh_from_db()
        assert order.status == "paid"

    @patch("apps.invoicing.tasks.send_order_confirmation_email")
    @patch("apps.invoicing.tasks.generate_invoice")
    def test_queues_async_tasks(
        self, mock_invoice, mock_email, order_with_payment
    ):
        """Per rule.md: email and invoice are Celery tasks, not synchronous."""
        order, payment = order_with_payment
        event = _make_succeeded_event("evt_test_004", "pi_test_123456")

        payment_services.handle_payment_succeeded(event)

        mock_email.delay.assert_called_once_with(order.id)
        mock_invoice.delay.assert_called_once_with(order.id)


@pytest.mark.django_db
class TestPaymentFailed:
    def test_payment_failure_cancels_order(self, order_with_payment):
        order, payment = order_with_payment
        event = _make_failed_event("evt_test_fail_001", "pi_test_123456")

        result = payment_services.handle_payment_failed(event)

        assert result is True
        order.refresh_from_db()
        payment.refresh_from_db()
        assert order.status == "cancelled"
        assert payment.status == "failed"

    def test_failure_releases_reservations(
        self, order_with_payment, variant
    ):
        order, payment = order_with_payment
        event = _make_failed_event("evt_test_fail_002", "pi_test_123456")

        payment_services.handle_payment_failed(event)

        variant.refresh_from_db()
        assert variant.reserved_quantity == 0
