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

from core.exceptions import PaymentServiceUnavailable

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
        # The storefront gets a clean 503 ("retry shortly") instead of an HTML 500.
        raise PaymentServiceUnavailable() from e


class PaymentIntentNotCancellable(Exception):
    """
    The PaymentIntent could not be proven cancelled.

    ``retryable`` tells the two situations apart:
      * False -> Stripe answered: the intent is paid / processing / in a final state.
                 The customer may genuinely have paid it.
      * True  -> Stripe could not be reached (network, 5xx, rate limit). Nothing is
                 known about the intent, so the caller should ask the customer to retry
                 instead of silently taking a decision.
    """

    def __init__(self, message="", retryable=False):
        super().__init__(message)
        self.retryable = retryable


def cancel_payment_intent(payment_intent_id):
    """
    Cancel a PaymentIntent so it can never be paid.

    A PaymentIntent that no longer exists at Stripe counts as cancelled.
    Any other failure raises PaymentIntentNotCancellable (see ``retryable``).
    """
    stripe = _get_stripe()
    try:
        stripe.PaymentIntent.cancel(payment_intent_id)
    except (stripe.error.APIConnectionError, stripe.error.APIError, stripe.error.RateLimitError) as e:
        raise PaymentIntentNotCancellable(str(e), retryable=True) from e
    except stripe.error.InvalidRequestError as e:
        if getattr(e, "code", None) == "resource_missing":
            return
        raise PaymentIntentNotCancellable(str(e), retryable=False) from e
    except stripe.error.StripeError as e:
        raise PaymentIntentNotCancellable(str(e), retryable=False) from e


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