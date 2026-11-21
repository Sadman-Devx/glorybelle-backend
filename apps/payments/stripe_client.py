"""
GLORYBELLE — Stripe Client.

Thin wrapper around the Stripe SDK.
Per rule.md:
  - "Never create a Stripe PaymentIntent without an idempotency key."
  - "Never let raw card data touch GLORYBELLE's servers."
  - "Never skip Stripe webhook signature verification."
"""
import logging

import stripe
from django.conf import settings

from apps.payments.models import Payment

logger = logging.getLogger(__name__)

# Configure Stripe — set per-call instead of module-load so test/live key
# switches (e.g. during deploy) are picked up without a process restart.
def _get_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_payment_intent(order):
    """
    Create a Stripe PaymentIntent for the given order.

    Returns:
        tuple: (client_secret, payment_intent_id)

    Per rule.md: always use an idempotency key to prevent double charges.

    IMPORTANT — Stripe idempotency contract:
    The idempotency_key must be DETERMINISTIC per order. If it includes any
    random component (uuid, timestamp, etc.), every retry creates a NEW
    PaymentIntent + Payment record, completely defeating the purpose.
    The key must be derived from order.order_number alone, so that any
    retried request (network timeout, double-click, Stripe-side retry)
    returns the original PaymentIntent instead of creating a new one.
    """
    stripe = _get_stripe()

    # Deterministic key — same order always produces the same key.
    # If this function is called twice for the same order (retry / double-click),
    # Stripe returns the original PaymentIntent instead of creating a new charge.
    idempotency_key = f"glorybelle_order_{order.order_number}"

    try:
        intent = stripe.PaymentIntent.create(
            amount=int(order.total * 100),  # Stripe expects cents
            currency="eur",
            metadata={
                "order_number": order.order_number,
                "email": order.email,
            },
            idempotency_key=idempotency_key,
        )

        # Idempotent Payment record creation — if this exact intent was already
        # recorded (e.g. webhook beat us to it, or a previous call succeeded
        # but the HTTP response was lost), don't try to create a duplicate.
        # The unique constraint on stripe_payment_intent_id will protect us,
        # but we use get_or_create to avoid raising IntegrityError.
        Payment.objects.get_or_create(
            stripe_payment_intent_id=intent.id,
            defaults={
                "order": order,
                "amount": order.total,
                "currency": "EUR",
                "status": "pending",
                "idempotency_key": idempotency_key,
            },
        )

        logger.info(
            "Created PaymentIntent %s for order %s (€%.2f)",
            intent.id,
            order.order_number,
            order.total,
        )

        return intent.client_secret, intent.id

    except stripe.error.StripeError as e:
        logger.error(
            "Stripe error creating PaymentIntent for order %s: %s",
            order.order_number,
            str(e),
        )
        raise


def verify_webhook_signature(payload, sig_header):
    """
    Verify a Stripe webhook signature.

    Per rule.md: "Never skip Stripe webhook signature verification,
    even in a rush to ship a fix — an unverified webhook endpoint
    can be spoofed to mark arbitrary orders paid."

    Returns:
        stripe.Event: the verified event object

    Raises:
        stripe.error.SignatureVerificationError: if verification fails
        ValueError: if the payload cannot be parsed as JSON
    """
    stripe = _get_stripe()
    return stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET,
    )