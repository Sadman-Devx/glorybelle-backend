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
from django.db.models import Sum

from apps.cart.models import Cart, StockReservation
from apps.catalog.models import ProductVariant
from apps.orders.models import Order

from .models import Payment, ProcessedWebhookEvent

logger = logging.getLogger(__name__)


class _PaymentNotFound(Exception):
    """Raised inside the atomic block so the ProcessedWebhookEvent row is rolled back."""


def _is_event_processed(stripe_event_id):
    """Check if this webhook event has already been processed."""
    return ProcessedWebhookEvent.objects.filter(
        stripe_event_id=stripe_event_id
    ).exists()


def release_order_reservations(order, deduct_stock=False):
    """Release only reservations associated with this order."""
    order_lines = list(
        order.items.values("variant_id")
        .annotate(quantity=Sum("quantity"))
        .order_by("variant_id")
    )
    reservations = list(
        StockReservation.objects.select_for_update()
        .filter(order=order, is_active=True)
        .values("variant_id", "quantity")
    )
    released_by_variant = {}
    for reservation in reservations:
        variant_id = reservation["variant_id"]
        released_by_variant[variant_id] = (
            released_by_variant.get(variant_id, 0) + reservation["quantity"]
        )
    if reservations:
        StockReservation.objects.filter(
            order=order, is_active=True
        ).update(is_active=False)

    sold_by_variant = {
        line["variant_id"]: line["quantity"] for line in order_lines
    } if deduct_stock else {}
    variant_ids = set(released_by_variant) | set(sold_by_variant)
    variants = list(
        ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_ids)
        .order_by("pk")
    )
    for variant in variants:
        variant.reserved_quantity = max(
            0,
            variant.reserved_quantity - released_by_variant.get(variant.pk, 0),
        )
        if deduct_stock:
            variant.stock_quantity = max(
                0, variant.stock_quantity - sold_by_variant.get(variant.pk, 0)
            )
    if variants:
        fields = ["reserved_quantity"]
        if deduct_stock:
            fields.append("stock_quantity")
        ProductVariant.objects.bulk_update(variants, fields)


def _lock_order_then_payment(payment_intent_id):
    """Use a consistent lock order with the pending-order expiry task."""
    try:
        payment_ref = Payment.objects.only("pk", "order_id").get(
            stripe_payment_intent_id=payment_intent_id
        )
    except Payment.DoesNotExist:
        raise _PaymentNotFound(payment_intent_id)

    order = Order.objects.select_for_update().get(pk=payment_ref.order_id)
    payment = Payment.objects.select_for_update().get(pk=payment_ref.pk)
    return order, payment


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

    Returns False (-> HTTP 500, so Stripe retries) when no Payment matches the
    PaymentIntent. In that case the whole transaction is rolled back, so the
    event is NOT recorded as processed and the retry is handled for real.
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

    try:
        with transaction.atomic():
            order = _mark_order_paid(
                stripe_event_id, payment_intent_id, stripe_charge_id
            )
    except _PaymentNotFound:
        logger.error("No Payment found for PaymentIntent %s", payment_intent_id)
        return False

    if order is None:  # duplicate delivery of an already-succeeded PaymentIntent
        return True

    # Step 5: Queue async tasks OUTSIDE the transaction.
    # Per rule.md: never call external services synchronously. A broker outage
    # must not turn an already-committed payment into an HTTP 500 (Stripe's
    # retry would be skipped as "already processed" and nothing would be sent),
    # so queueing failures are logged loudly instead of raised.
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
    except Exception:  # noqa: BLE001 — broker/connection errors of any kind
        logger.exception(
            "Could not queue confirmation email / invoice for PAID order %s — "
            "re-queue manually",
            order.order_number,
        )

    return True


def _mark_order_paid(stripe_event_id, payment_intent_id, stripe_charge_id):
    """
    Runs inside transaction.atomic(). Returns the Order that was just marked
    paid, or None if this PaymentIntent had already succeeded.
    Raises _PaymentNotFound (rolling everything back) for an unknown PaymentIntent.
    """
    # Record the event FIRST to prevent double-processing
    ProcessedWebhookEvent.objects.create(
        stripe_event_id=stripe_event_id,
        event_type="payment_intent.succeeded",
    )

    order, payment = _lock_order_then_payment(payment_intent_id)

    # Same PaymentIntent delivered again under a NEW event id: stock must not
    # be deducted twice.
    if payment.status == "succeeded":
        logger.info(
            "PaymentIntent %s already succeeded — event %s ignored",
            payment_intent_id,
            stripe_event_id,
        )
        return None

    if order.status == "cancelled":
        # Customer paid an order that had been cancelled (e.g. superseded by a
        # newer checkout). The money is real, so it is recorded as paid — but
        # make it impossible to miss.
        logger.error(
            "PAYMENT RECEIVED FOR CANCELLED ORDER %s (%s) — fulfil or refund manually",
            order.order_number,
            payment_intent_id,
        )

    payment.status = "succeeded"
    payment.stripe_charge_id = stripe_charge_id
    payment.save(update_fields=["status", "stripe_charge_id", "updated_at"])

    order.status = "paid"
    order.save(update_fields=["status", "updated_at"])

    # Step 3: Convert this order's reservations into stock deductions.
    release_order_reservations(order, deduct_stock=True)

    # Step 4: Clear the user's cart (only for logged-in users — guest carts are
    # cleared by the storefront after payment / the periodic expiry task).
    if order.user:
        Cart.objects.filter(user=order.user).delete()

    logger.info(
        "Payment succeeded for order %s (PaymentIntent %s)",
        order.order_number,
        payment_intent_id,
    )
    return order


def handle_payment_failed(event):
    """
    Handle a payment_intent.payment_failed webhook event.

    Marks the Payment as failed, Order as cancelled, and releases
    stock reservations (scoped to this order — P0 fix #2).

    Like the success handler, an unknown PaymentIntent rolls the transaction
    back (event not marked processed) and returns False so Stripe retries.
    A failure event for a payment that has ALREADY succeeded is ignored: a late
    or out-of-order failure must never cancel a paid order.
    """
    stripe_event_id = event["id"]
    payment_intent = event["data"]["object"]
    payment_intent_id = payment_intent["id"]

    if _is_event_processed(stripe_event_id):
        logger.info(
            "Webhook event %s already processed — skipping", stripe_event_id
        )
        return True

    try:
        with transaction.atomic():
            ProcessedWebhookEvent.objects.create(
                stripe_event_id=stripe_event_id,
                event_type="payment_intent.payment_failed",
            )

            order, payment = _lock_order_then_payment(payment_intent_id)

            if payment.status == "succeeded" or order.status in {
                "paid", "processing", "shipped", "delivered"
            }:
                logger.warning(
                    "Failure event %s for already-succeeded PaymentIntent %s ignored",
                    stripe_event_id,
                    payment_intent_id,
                )
                return True

            payment.status = "failed"
            payment.save(update_fields=["status", "updated_at"])

            order.status = "cancelled"
            order.save(update_fields=["status", "updated_at"])

            release_order_reservations(order)

            logger.info(
                "Payment failed for order %s — reservations released (scoped to this order)",
                order.order_number,
            )
    except _PaymentNotFound:
        logger.error(
            "No Payment found for failed PaymentIntent %s", payment_intent_id
        )
        return False

    return True
