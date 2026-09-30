"""
GLORYBELLE — Wishlist Views.

Per PRD §3.2: heart toggle — add if absent, remove if present.
Per design.md §1.3: "colored rosewood when active."
"""
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product

from .models import WishlistItem
from .serializers import WishlistItemSerializer, WishlistToggleSerializer


class WishlistListView(generics.ListAPIView):
    """
    GET /api/wishlist/

    List the authenticated user's wishlist items with product details.
    """

    serializer_class = WishlistItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            WishlistItem.objects.filter(user=self.request.user)
            .select_related("product__category")
            .prefetch_related("product__variants", "product__images")
        )


class WishlistToggleView(APIView):
    """
    POST /api/wishlist/toggle/

    Toggle a product in the user's wishlist.
    If the product is already in the wishlist, remove it.
    If not, add it.

    Returns:
        {"wishlisted": true/false, "product_id": int}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WishlistToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data["product_id"]

        # Verify product exists and is active
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "detail": "Prodotto non trovato."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Toggle
        item, created = WishlistItem.objects.get_or_create(
            user=request.user,
            product=product,
        )

        if not created:
            # Already in wishlist — remove it
            item.delete()
            return Response(
                {"wishlisted": False, "product_id": product_id},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"wishlisted": True, "product_id": product_id},
            status=status.HTTP_201_CREATED,
        )
