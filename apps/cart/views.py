"""
GLORYBELLE — Cart Views.

Thin HTTP adapter — all logic in services.py (rule.md).
Supports both authenticated users and guest sessions.

P1 fix #10: adds DELETE /api/cart/ (clear entire cart) endpoint.
"""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from . import services
from .guest import guest_cart_key
from .serializers import (
    AddToCartSerializer,
    CartSerializer,
    UpdateCartItemSerializer,
)


def _get_cart(request, create=True):
    """
    Resolve the cart for this request.

    1. logged-in user          -> the user's cart
    2. X-Cart-Token header     -> the guest cart for that token (cookie-less, works cross-domain)
    3. Django session cookie   -> legacy fallback

    With ``create=False`` a read-only request for an unknown token returns None instead of
    inserting a row (otherwise anyone could fill the table by sending random tokens).
    """
    if request.user.is_authenticated:
        return services.get_or_create_cart(user=request.user)

    key = guest_cart_key(request)
    if key:
        if create:
            return services.get_or_create_cart(session_key=key)
        from .models import Cart

        return Cart.objects.filter(session_key=key, user__isnull=True).first()

    # Legacy cookie-based guest session
    if not request.session.session_key:
        request.session.create()
    return services.get_or_create_cart(session_key=request.session.session_key)


EMPTY_CART = {
    "id": None,
    "items": [],
    "total": "0.00",
    "item_count": 0,
    "discount": None,
    "total_after_discount": "0.00",
    "created_at": None,
    "updated_at": None,
}


class CartView(APIView):
    """
    GET    /api/cart/  → current cart with items
    DELETE /api/cart/  → clear the whole cart (P1 fix #10)
    """

    permission_classes = [AllowAny]
    serializer_class = CartSerializer

    def get(self, request):
        cart = _get_cart(request, create=False)
        if cart is None:
            return Response(EMPTY_CART)
        serializer = CartSerializer(cart, context={"request": request})
        return Response(serializer.data)

    def delete(self, request):
        """Clear the entire cart — remove all items + release all reservations."""
        cart = _get_cart(request)
        services.clear_cart(cart=cart)
        cart.refresh_from_db()
        return Response(
            CartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class CartItemView(APIView):
    """
    POST   /api/cart/items/      → add item to cart
    PATCH  /api/cart/items/{id}/  → update item quantity
    DELETE /api/cart/items/{id}/  → remove item from cart
    """

    permission_classes = [AllowAny]
    serializer_class = CartSerializer

    @extend_schema(request=AddToCartSerializer, responses=CartSerializer)
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

    @extend_schema(request=UpdateCartItemSerializer, responses=CartSerializer)
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

    @extend_schema(request=None, responses=CartSerializer)
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
    POST /api/cart/merge/ -> merge the guest cart of THIS browser into the
    authenticated user's cart (call right after login).

    The guest cart is identified by what only this browser holds: the X-Cart-Token
    header (and, for old sessions, the HttpOnly Django session cookie). A ``session_key``
    in the body is deliberately ignored: honouring a client-supplied key would let any
    logged-in user pull another visitor's cart into their own.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    def post(self, request):
        keys = []
        token_key = guest_cart_key(request)
        if token_key:
            keys.append(token_key)
        if request.session.session_key:
            keys.append(request.session.session_key)
        for key in keys:
            services.merge_carts(key, request.user)

        cart = services.get_or_create_cart(user=request.user)
        return Response(
            CartSerializer(cart, context={"request": request}).data,
        )
