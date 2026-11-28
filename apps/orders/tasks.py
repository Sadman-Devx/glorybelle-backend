"""Periodic cleanup for stale unpaid orders."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.services import release_order_reservations
from apps.payments.stripe_client import (
    PaymentIntentNotCancellable,
    cancel_payment_intent,
)

logger = logging.getLogger(__name__)


@shared_task(name="apps.orders.tasks.cancel_expired_pending_orders")
def cancel_expired_pending_orders(batch_size=100):
    """Cancel old pending orders only after Stripe confirms their intent is cancellable."""
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer.")

    cutoff = timezone.now() - timedelta(
        minutes=settings.ORDER_PENDING_EXPIRY_MINUTES
    )
    order_ids = list(
        Order.objects.filter(status="pending", created_at__lt=cutoff)
        .filter(
            Q(payment__isnull=True)
            | ~Q(payment__status__in=("succeeded", "processing", "refunded"))
        )
        .order_by("created_at", "pk")
        .values_list("pk", flat=True)[:batch_size]
    )
    cancelled_count = 0

    for order_id in order_ids:
        try:
            with transaction.atomic():
                try:
                    order = Order.objects.select_for_update().get(pk=order_id)
                except Order.DoesNotExist:
                    continue
                if order.status != "pending" or order.created_at >= cutoff:
                    continue

                payment = (
                    Payment.objects.select_for_update()
                    .filter(order_id=order.pk)
                    .first()
                )
                if payment and payment.status in {
                    "succeeded", "processing", "refunded"
                }:
                    continue

                payment_intent_id = (
                    payment.stripe_payment_intent_id
                    if payment
                    else order.stripe_payment_intent_id
                )
                if payment_intent_id:
                    try:
                        cancel_payment_intent(payment_intent_id)
                    except PaymentIntentNotCancellable as exc:
                        logger.warning(
                            "Pending order %s was not expired; Stripe could not "
                            "confirm cancellation (retryable=%s)",
                            order.order_number,
                            exc.retryable,
                        )
                        continue

                if payment and payment.status == "pending":
                    payment.status = "failed"
                    payment.save(update_fields=["status", "updated_at"])

                order.status = "cancelled"
                order.save(update_fields=["status", "updated_at"])
                release_order_reservations(order)
                cancelled_count += 1
                logger.info(
                    "Expired pending order %s; Stripe intent cancelled and "
                    "order reservations released",
                    order.order_number,
                )
        except Exception:
            logger.exception(
                "Could not expire pending order id=%s; it will be retried",
                order_id,
            )

    return cancelled_count
