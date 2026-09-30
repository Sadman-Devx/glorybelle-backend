"""
GLORYBELLE — Cart Views.

Thin HTTP adapter — all logic in services.py (rule.md).
Supports both authenticated users and guest sessions.
"""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    AddToCartSerializer,
    CartSerializer,
    UpdateCartItemSerializer,
)


def _get_cart(request):
    """Get or create cart for the current request (user or guest session)."""
    if request.user.is_authenticated:
        return services.get_or_create_cart(user=request.user)
    else:
        # Ensure session exists for guest
        if not request.session.session_key:
            request.session.create()
        return services.get_or_create_cart(session_key=request.session.session_key)


class CartView(APIView):
    """
    GET /api/cart/ → current cart with items
    """

    permission_classes = [AllowAny]

    def get(self, request):
        cart = _get_cart(request)
        serializer = CartSerializer(cart, context={"request": request})
        return Response(serializer.data)


class CartItemView(APIView):
    """
    POST   /api/cart/items/      → add item to cart
    PATCH  /api/cart/items/{id}/  → update item quantity
    DELETE /api/cart/items/{id}/  → remove item from cart
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """Add a product variant to the cart."""
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = _get_cart(request)
        cart_item = services.add_to_cart(
            cart=cart,
            variant_id=serializer.validated_data["variant_id"],
            quantity=serializer.validated_data["quantity"],
        )

        # Return updated cart
        cart.refresh_from_db()
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, item_id=None):
        """Update cart item quantity."""
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = _get_cart(request)
        services.update_cart_item_quantity(
            cart=cart,
            cart_item_id=item_id,
            new_quantity=serializer.validated_data["quantity"],
        )

        cart.refresh_from_db()
        return Response(
            CartSerializer(cart, context={"request": request}).data,
        )

    def delete(self, request, item_id=None):
        """Remove an item from the cart."""
        cart = _get_cart(request)
        services.remove_from_cart(cart=cart, cart_item_id=item_id)

        cart.refresh_from_db()
        return Response(
            CartSerializer(cart, context={"request": request}).data,
        )


class CartMergeView(APIView):
    """
    POST /api/cart/merge/ → merge guest cart into user cart on login.
    """

    def post(self, request):
        session_key = request.data.get("session_key")
        if session_key and request.user.is_authenticated:
            services.merge_carts(session_key, request.user)

        cart = services.get_or_create_cart(user=request.user)
        return Response(
            CartSerializer(cart, context={"request": request}).data,
        )
