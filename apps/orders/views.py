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
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cart.models import Cart
from apps.cart.views import _get_cart
from apps.payments.stripe_client import create_payment_intent
from core.exceptions import CheckoutConflict
from core.throttling import ScopedRateThrottle

from . import services
from .models import Order
from .serializers import (
    CheckoutSerializer,
    OrderGuestLookupSerializer,
    OrderListSerializer,
    OrderSerializer,
)

logger = logging.getLogger(__name__)


def _checkout_response(order, replay=False):
    client_secret, payment_intent_id = create_payment_intent(order)
    if order.stripe_payment_intent_id != payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id
        order.save(update_fields=["stripe_payment_intent_id"])

    response_data = {
        "order": OrderSerializer(order).data,
        "client_secret": client_secret,
        "payment_intent_id": payment_intent_id,
    }
    if replay:
        response_data["idempotent_replay"] = True
    return Response(
        response_data,
        status=status.HTTP_200_OK if replay else status.HTTP_201_CREATED,
    )


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

        cart = _get_cart(request)
        user = request.user if request.user.is_authenticated else None
        idempotency_key = data.get("idempotency_key")

        # Serialize checkout attempts for the same cart through Stripe creation too.
        with transaction.atomic():
            cart = Cart.objects.select_for_update().get(pk=cart.pk)

            if idempotency_key:
                existing = (
                    Order.objects.select_for_update()
                    .filter(idempotency_key=idempotency_key)
                    .first()
                )
                if existing:
                    if (
                        existing.cart_id != cart.pk
                        or existing.status == "cancelled"
                        or not services.checkout_matches_order(
                            existing, cart, data, user
                        )
                    ):
                        raise CheckoutConflict(
                            "La chiave di checkout è già stata usata per un ordine diverso."
                        )
                    return _checkout_response(existing, replay=True)

            replay_window = timedelta(
                minutes=getattr(settings, "STOCK_RESERVATION_MINUTES", 15)
            )
            replay_cutoff = timezone.now() - replay_window
            pending_orders = list(
                Order.objects.select_for_update()
                .filter(cart=cart, status="pending")
                .order_by("-created_at")
            )
            replay_order = None
            for pending_order in pending_orders:
                same_checkout = services.checkout_matches_order(
                    pending_order, cart, data, user
                )
                if (
                    replay_order is None
                    and same_checkout
                    and pending_order.created_at >= replay_cutoff
                ):
                    replay_order = pending_order
                else:
                    services.supersede_pending_checkout_order(pending_order)

            if replay_order:
                return _checkout_response(replay_order, replay=True)

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
            return _checkout_response(order)


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


class OrderGuestLookupView(APIView):
    """
    POST /api/orders/lookup/   body: {order_number, email}

    Lets a GUEST (no account) read back the order they just placed, so the
    confirmation page can poll its payment status. Both fields must match;
    any mismatch returns the same generic 404 so order numbers cannot be
    probed. Rate limited (scope ``order_lookup``).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "order_lookup"
    serializer_class = OrderGuestLookupSerializer

    def post(self, request):
        serializer = OrderGuestLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = (
            Order.objects.filter(
                order_number=serializer.validated_data["order_number"].strip(),
                email__iexact=serializer.validated_data["email"].strip(),
            )
            .prefetch_related("items")
            .first()
        )
        if order is None:
            return Response(
                {"error": {"code": "not_found", "detail": "Ordine non trovato."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrderSerializer(order).data)
