"""
GLORYBELLE — Stripe Client.

Thin wrapper around the Stripe SDK.
Per rule.md:
  - "Never create a Stripe PaymentIntent without an idempotency key."
  - "Never let raw card data touch GLORYBELLE's servers."
  - "Never skip Stripe webhook signature verification."
"""
import logging
import uuid

import stripe
from django.conf import settings

from apps.payments.models import Payment

logger = logging.getLogger(__name__)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(order):
    """
    Create a Stripe PaymentIntent for the given order.

    Returns:
        tuple: (client_secret, payment_intent_id)

    Per rule.md: always use an idempotency key to prevent double charges.
    """
    idempotency_key = f"glorybelle_order_{order.order_number}_{uuid.uuid4().hex[:8]}"

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

        # Create Payment record
        Payment.objects.create(
            order=order,
            stripe_payment_intent_id=intent.id,
            amount=order.total,
            currency="EUR",
            status="pending",
            idempotency_key=idempotency_key,
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
    """
    return stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.STRIPE_WEBHOOK_SECRET,
    )
