import logging
from decimal import Decimal

import stripe
from django.core.cache import cache
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import APIException
from simple_history.utils import update_change_reason

from apps.orders.models import Order, OrderAdminNote
from apps.payments.models import Payment
from apps.payments.stripe_client import _get_stripe

logger = logging.getLogger(__name__)

ALLOWED_ORDER_TRANSITIONS = {
    "pending": frozenset(),
    "paid": frozenset({"processing", "shipped"}),
    "processing": frozenset({"shipped"}),
    "shipped": frozenset({"delivered"}),
    "delivered": frozenset(),
    "cancelled": frozenset(),
    "refunded": frozenset(),
}

CANCELLABLE_ORDER_STATUSES = frozenset({"pending", "paid", "processing"})
PAID_ORDER_STATUSES = frozenset({"paid", "processing", "shipped", "delivered"})


class OrderActionConflict(APIException):
    status_code = 409
    default_detail = "L'azione non è consentita per lo stato attuale dell'ordine."
    default_code = "order_conflict"


class RefundProcessingError(APIException):
    status_code = 502
    default_detail = "Non è stato possibile elaborare il rimborso Stripe."
    default_code = "refund_failed"


def _locked_order(order_id):
    try:
        return Order.objects.select_for_update().get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise Http404("Ordine non trovato.") from exc


def _save_order_change(order, actor, reason, update_fields):
    order._history_user = actor
    order.save(update_fields=update_fields)
    update_change_reason(order, reason)


def _latest_audit_event(order):
    record = order.history.select_related("history_user").first()
    return {
        "id": record.history_id,
        "action": record.status,
        "timestamp": record.history_date,
        "actor_id": record.history_user_id,
        "reason": record.history_change_reason,
    }


def transition_order(order_id, actor, target_status, tracking_number=None):
    with transaction.atomic():
        order = _locked_order(order_id)
        if target_status not in ALLOWED_ORDER_TRANSITIONS.get(order.status, ()):
            raise OrderActionConflict(
                f"Transizione non consentita: {order.status} → {target_status}."
            )

        previous_status = order.status
        order.status = target_status
        update_fields = ["status", "updated_at"]
        if target_status == "shipped" and tracking_number is not None:
            order.tracking_number = tracking_number
            update_fields.append("tracking_number")

        _save_order_change(
            order,
            actor,
            f"Stato modificato da {previous_status} a {target_status}.",
            update_fields,
        )
        cache.delete("admin:dashboard:v1")
        return order, _latest_audit_event(order)


def _create_full_refund(order, payment):
    if payment.status != "succeeded":
        raise OrderActionConflict(
            "Il pagamento non risulta completato e non può essere rimborsato."
        )
    if (
        payment.currency.upper() != "EUR"
        or payment.amount <= Decimal("0.00")
        or payment.amount != order.total
        or payment.stripe_payment_intent_id != order.stripe_payment_intent_id
    ):
        raise OrderActionConflict(
            "Importo o riferimento del pagamento non corrispondente all'ordine."
        )

    amount_minor = int(payment.amount * 100)
    if Decimal(amount_minor) / Decimal("100") != payment.amount:
        raise OrderActionConflict("L'importo del pagamento non è valido.")

    try:
        refund = _get_stripe().Refund.create(
            payment_intent=payment.stripe_payment_intent_id,
            amount=amount_minor,
            idempotency_key=f"glorybelle-order-cancel-{order.pk}-refund-v1",
            metadata={"order_number": order.order_number},
        )
    except stripe.error.StripeError as exc:
        logger.exception("Stripe refund failed for order %s", order.order_number)
        raise RefundProcessingError() from exc

    refund_id = refund.get("id")
    refund_status = refund.get("status")
    if not refund_id or refund_status not in {
        "pending",
        "succeeded",
    }:
        logger.error("Stripe returned an invalid refund response for order %s", order.pk)
        raise RefundProcessingError()

    payment.stripe_refund_id = refund_id
    payment.stripe_refund_status = refund_status
    if refund_status == "succeeded":
        payment.status = "refunded"
    payment.save(
        update_fields=[
            "stripe_refund_id",
            "stripe_refund_status",
            "status",
            "updated_at",
        ]
    )
    return refund_id


def cancel_order(order_id, actor, reason):
    with transaction.atomic():
        order = _locked_order(order_id)
        if order.status not in CANCELLABLE_ORDER_STATUSES:
            raise OrderActionConflict(
                f"L'ordine con stato {order.status} non può essere annullato."
            )

        payment = Payment.objects.select_for_update().filter(order=order).first()
        payment_succeeded = payment is not None and payment.status == "succeeded"
        order_already_paid = order.status in PAID_ORDER_STATUSES
        if order_already_paid and not payment_succeeded:
            raise OrderActionConflict(
                "Il pagamento dell'ordine non risulta verificato da Stripe."
            )

        if payment_succeeded:
            _create_full_refund(order, payment)

        order.status = "cancelled"
        _save_order_change(order, actor, reason, ["status", "updated_at"])
        cache.delete("admin:dashboard:v1")
        return order, _latest_audit_event(order)


def archive_order(order_id, actor, reason):
    with transaction.atomic():
        order = _locked_order(order_id)
        if order.archived_at is not None:
            raise OrderActionConflict("L'ordine è già archiviato.")

        order.archived_at = timezone.now()
        order.archive_reason = reason
        _save_order_change(
            order,
            actor,
            reason,
            ["archived_at", "archive_reason", "updated_at"],
        )
        return order, _latest_audit_event(order)


def create_order_note(order_id, actor, body):
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise Http404("Ordine non trovato.") from exc
    return OrderAdminNote.objects.create(order=order, author=actor, body=body)
