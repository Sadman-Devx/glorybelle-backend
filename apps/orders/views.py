"""
GLORYBELLE — Order Views.

Thin HTTP adapter — all logic in services.py (rule.md).

P1 fix #9: OrderHistoryView now annotates item_count via Count("items") instead
of calling obj.items.count() per row (which fires a COUNT query per order,
triggering N+1 on /api/orders/).

P1 fix #8: CheckoutView now accepts an optional client-supplied idempotency_key
(UUID per checkout attempt). If provided, it's used as the Order.idempotency_key
AND passed to Stripe as the PaymentIntent idempotency_key. Retries with the same
key return the original order instead of creating a duplicate.
"""
import logging

from django.db.models import Count
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.views import _get_cart
from apps.payments.stripe_client import create_payment_intent

from . import services
from .models import Order
from .serializers import CheckoutSerializer, OrderListSerializer, OrderSerializer

logger = logging.getLogger(__name__)


class CheckoutView(APIView):
    """
    POST /api/checkout/

    Creates an Order from the current cart + a Stripe PaymentIntent.
    Returns the Stripe client_secret for frontend payment confirmation.

    Per architecture.md §1.3:
      Browser → POST /api/checkout/ → Django creates Order (pending)
      + Stripe PaymentIntent → returns client_secret

    Idempotency (P1 fix #8):
      Client sends an `idempotency_key` UUID in the request body (one per
      checkout attempt). The same key on a retried request returns the
      original order — no duplicate charge, no duplicate PaymentIntent.
    """

    permission_classes = [AllowAny]
    serializer_class = CheckoutSerializer

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Idempotency: if the client sent a key and an Order already exists
        # with that key, return the existing order instead of creating a new one.
        idempotency_key = data.get("idempotency_key")
        if idempotency_key:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                # Return the existing order + a fresh client_secret (the
                # PaymentIntent still exists on Stripe's side; we just need
                # to give the client a secret to retry confirmation).
                # Note: create_payment_intent is itself idempotent (same order
                # → same PaymentIntent via stripe_client.py's deterministic key).
                client_secret, _ = create_payment_intent(existing)
                return Response(
                    {
                        "order": OrderSerializer(existing).data,
                        "client_secret": client_secret,
                        "payment_intent_id": existing.stripe_payment_intent_id,
                        "idempotent_replay": True,
                    },
                    status=status.HTTP_200_OK,
                )

        cart = _get_cart(request)

        # Determine user
        user = request.user if request.user.is_authenticated else None

        # Create order from cart (services.py — all business logic there)
        order = services.create_order_from_cart(
            cart=cart,
            email=data["email"],
            shipping_address_id=data.get("shipping_address_id"),
            shipping_address_data=data.get("shipping_address"),
            billing_address_id=data.get("billing_address_id"),
            billing_address_data=data.get("billing_address"),
            billing_same_as_shipping=data.get("billing_same_as_shipping", True),
            user=user,
            notes=data.get("notes", ""),
            idempotency_key=idempotency_key,
        )

        # Create Stripe PaymentIntent — uses order.order_number as the Stripe
        # idempotency key (P0 fix #1, deterministic).
        client_secret, payment_intent_id = create_payment_intent(order)

        # Store the PaymentIntent ID on the order
        order.stripe_payment_intent_id = payment_intent_id
        order.save(update_fields=["stripe_payment_intent_id"])

        return Response(
            {
                "order": OrderSerializer(order).data,
                "client_secret": client_secret,
                "payment_intent_id": payment_intent_id,
            },
            status=status.HTTP_201_CREATED,
        )


class OrderHistoryView(generics.ListAPIView):
    """
    GET /api/orders/

    List the authenticated user's orders, most recent first.

    P1 fix #9: annotate(Count("items")) eliminates the N+1 query that
    OrderListSerializer.get_item_count was triggering via obj.items.count()
    per row. Now the COUNT is done in a single SQL query.
    """

    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .annotate(item_count_annotated=Count("items"))
            .prefetch_related("items")
            .order_by("-created_at")
        )


class OrderDetailView(generics.RetrieveAPIView):
    """
    GET /api/orders/{order_number}/

    Retrieve a single order by order number. Owner-scoped.
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "order_number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items"
        )
