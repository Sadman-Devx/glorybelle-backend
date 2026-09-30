"""
GLORYBELLE — Cart Celery Tasks.

Per architecture.md: expired stock reservation cleanup runs every 60s via Celery beat.
Per rule.md: select_for_update blocks should do minimum work and commit.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant

from .models import StockReservation

logger = logging.getLogger(__name__)


@shared_task(name="apps.cart.tasks.release_expired_reservations")
def release_expired_reservations():
    """
    Release expired stock reservations.

    Runs every 60 seconds via Celery beat (configured in config/celery.py).

    Flow:
    1. Find all active reservations where expires_at < now
    2. For each, within a transaction:
       a. Lock the variant row (select_for_update)
       b. Decrement reserved_quantity
       c. Deactivate the reservation
    """
    now = timezone.now()
    expired = StockReservation.objects.filter(
        is_active=True,
        expires_at__lt=now,
    ).select_related("variant")

    count = 0
    for reservation in expired:
        with transaction.atomic():
            # Lock the variant row — minimum work inside the lock
            variant = (
                ProductVariant.objects.select_for_update()
                .get(id=reservation.variant_id)
            )
            variant.reserved_quantity = max(
                0, variant.reserved_quantity - reservation.quantity
            )
            variant.save(update_fields=["reserved_quantity"])

            reservation.is_active = False
            reservation.save(update_fields=["is_active"])
            count += 1

    if count > 0:
        logger.info("Released %d expired stock reservation(s)", count)

    return count
