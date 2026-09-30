"""
GLORYBELLE — Payment Views.

Stripe webhook endpoint.
Per rule.md:
  - "Never skip Stripe webhook signature verification"
  - "Never mark an order 'paid' from the client-side redirect alone"
"""
import logging

from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import services
from .stripe_client import verify_webhook_signature

logger = logging.getLogger(__name__)


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def stripe_webhook_view(request):
    """
    POST /api/webhooks/stripe/

    Receives Stripe webhook events. Verifies signature, then dispatches
    to the appropriate handler.

    Per architecture.md §1.3:
      Stripe → sends payment_intent.succeeded webhook
      Django → verifies event hasn't been processed before,
              marks Order paid, decrements real stock,
              queues Celery tasks

    Per rule.md:
      "Never skip Stripe webhook signature verification, even in a rush
      to ship a fix — an unverified webhook endpoint can be spoofed to
      mark arbitrary orders paid."
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    # Step 1: Verify webhook signature
    try:
        event = verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.warning("Stripe webhook signature verification failed: %s", e)
        return Response(
            {"error": "Firma webhook non valida."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Step 2: Dispatch to handler based on event type
    event_type = event.get("type", "")
    logger.info("Received Stripe webhook: %s (%s)", event_type, event["id"])

    if event_type == "payment_intent.succeeded":
        success = services.handle_payment_succeeded(event)
    elif event_type == "payment_intent.payment_failed":
        success = services.handle_payment_failed(event)
    else:
        logger.info("Unhandled webhook event type: %s", event_type)
        return Response({"received": True}, status=status.HTTP_200_OK)

    if success:
        return Response({"received": True}, status=status.HTTP_200_OK)

    return Response(
        {"error": "Errore nell'elaborazione dell'evento."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
