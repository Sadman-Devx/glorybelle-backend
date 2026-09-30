"""
GLORYBELLE — Payment Services.

Idempotent webhook handling — the core payment reconciliation logic.

Per rule.md:
  - "Avoid business logic in views.py"
  - "Never process a Stripe webhook without checking ProcessedWebhookEvent first"
  - "Never touch stock_quantity or reserved_quantity outside
    select_for_update() inside transaction.atomic()"
  - "Never call Stripe, Fattura24, or SendGrid synchronously
    inside a request/response cycle — these are Celery tasks"

Per architecture.md §1.3:
  Stripe webhook is the SOURCE OF TRUTH for "was this order actually paid."
  On payment_intent.succeeded:
    1. Check idempotency
    2. Mark Order paid
    3. Convert reservations into actual stock deductions
    4. Queue async tasks (email, invoice)
"""
import logging

from django.db import transaction

from apps.cart.models import Cart, StockReservation
from apps.catalog.models import ProductVariant
from apps.orders.models import Order

from .models import Payment, ProcessedWebhookEvent

logger = logging.getLogger(__name__)


def _is_event_processed(stripe_event_id):
    """Check if this webhook event has already been processed."""
    return ProcessedWebhookEvent.objects.filter(
        stripe_event_id=stripe_event_id
    ).exists()


def handle_payment_succeeded(event):
    """
    Handle a payment_intent.succeeded webhook event.

    This is the most critical function in the payment flow:
    1. Check idempotency (ProcessedWebhookEvent)
    2. Mark Order paid
    3. Convert stock reservations into actual deductions
    4. Clear the user's cart
    5. Queue async tasks (email + invoice)

    Per roadmap Day 7: "replaying the same webhook payload twice results
    in the order being marked paid exactly once, not double-processed."
    """
    stripe_event_id = event["id"]
    payment_intent = event["data"]["object"]
    payment_intent_id = payment_intent["id"]
    stripe_charge_id = ""

    # Extract charge ID if available
    charges = payment_intent.get("charges", {})
    if charges and charges.get("data"):
        stripe_charge_id = charges["data"][0].get("id", "")

    # Step 1: Idempotency check
    if _is_event_processed(stripe_event_id):
        logger.info(
            "Webhook event %s already processed — skipping", stripe_event_id
        )
        return True  # Already processed, return success

    with transaction.atomic():
        # Record the event FIRST to prevent double-processing
        ProcessedWebhookEvent.objects.create(
            stripe_event_id=stripe_event_id,
            event_type="payment_intent.succeeded",
        )

        # Find the Payment and Order
        try:
            payment = Payment.objects.select_for_update().get(
                stripe_payment_intent_id=payment_intent_id
            )
        except Payment.DoesNotExist:
            logger.error(
                "No Payment found for PaymentIntent %s", payment_intent_id
            )
            return False

        order = payment.order

        # Update Payment
        payment.status = "succeeded"
        payment.stripe_charge_id = stripe_charge_id
        payment.save(update_fields=["status", "stripe_charge_id", "updated_at"])

        # Update Order status
        order.status = "paid"
        order.save(update_fields=["status", "updated_at"])

        # Step 3: Convert reservations into actual stock deductions
        # For each order item, decrement the real stock and deactivate reservations
        for order_item in order.items.all():
            variant = (
                ProductVariant.objects.select_for_update()
                .get(id=order_item.variant_id)
            )

            # Decrement actual stock
            variant.stock_quantity = max(
                0, variant.stock_quantity - order_item.quantity
            )

            # Find and deactivate the reservations for this variant
            # We deactivate all active reservations tied to the cart items
            # that generated this order's line items
            active_reservations = StockReservation.objects.filter(
                variant=variant,
                is_active=True,
                cart_item__cart__user=order.user,
            )

            total_released = 0
            for reservation in active_reservations:
                reservation.is_active = False
                reservation.save(update_fields=["is_active"])
                total_released += reservation.quantity

            # Decrement reserved_quantity
            variant.reserved_quantity = max(
                0, variant.reserved_quantity - total_released
            )
            variant.save(
                update_fields=["stock_quantity", "reserved_quantity"]
            )

        # Step 4: Clear the user's cart
        if order.user:
            Cart.objects.filter(user=order.user).delete()

        logger.info(
            "Payment succeeded for order %s (PaymentIntent %s)",
            order.order_number,
            payment_intent_id,
        )

    # Step 5: Queue async tasks OUTSIDE the transaction
    # Per rule.md: never call external services synchronously
    try:
        from apps.invoicing.tasks import (
            generate_invoice,
            send_order_confirmation_email,
        )

        send_order_confirmation_email.delay(order.id)
        generate_invoice.delay(order.id)
    except ImportError:
        logger.warning(
            "Invoicing tasks not available — skipping async tasks for order %s",
            order.order_number,
        )

    return True


def handle_payment_failed(event):
    """
    Handle a payment_intent.payment_failed webhook event.

    Marks the Payment as failed, Order as cancelled, and releases
    all stock reservations.
    """
    stripe_event_id = event["id"]
    payment_intent = event["data"]["object"]
    payment_intent_id = payment_intent["id"]

    if _is_event_processed(stripe_event_id):
        logger.info(
            "Webhook event %s already processed — skipping", stripe_event_id
        )
        return True

    with transaction.atomic():
        ProcessedWebhookEvent.objects.create(
            stripe_event_id=stripe_event_id,
            event_type="payment_intent.payment_failed",
        )

        try:
            payment = Payment.objects.select_for_update().get(
                stripe_payment_intent_id=payment_intent_id
            )
        except Payment.DoesNotExist:
            logger.error(
                "No Payment found for failed PaymentIntent %s",
                payment_intent_id,
            )
            return False

        order = payment.order

        payment.status = "failed"
        payment.save(update_fields=["status", "updated_at"])

        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])

        # Release all stock reservations for items in this order
        for order_item in order.items.all():
            variant = (
                ProductVariant.objects.select_for_update()
                .get(id=order_item.variant_id)
            )

            active_reservations = StockReservation.objects.filter(
                variant=variant,
                is_active=True,
            )

            total_released = 0
            for reservation in active_reservations:
                reservation.is_active = False
                reservation.save(update_fields=["is_active"])
                total_released += reservation.quantity

            variant.reserved_quantity = max(
                0, variant.reserved_quantity - total_released
            )
            variant.save(update_fields=["reserved_quantity"])

        logger.info(
            "Payment failed for order %s — reservations released",
            order.order_number,
        )

    return True
