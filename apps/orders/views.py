"""
GLORYBELLE — Order Views.

Thin HTTP adapter — all logic in services.py (rule.md).
"""
import logging

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
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

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
        )

        # Create Stripe PaymentIntent
        # Per rule.md: never create a PaymentIntent without an idempotency key
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
    """

    serializer_class = OrderListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
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
