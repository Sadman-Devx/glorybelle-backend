"""
GLORYBELLE — Review Views.

Per PRD §3.4: reviews are moderated — only approved reviews show publicly.
"""
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Product

from .models import Review
from .serializers import ReviewCreateSerializer, ReviewSerializer


class ProductReviewListView(generics.ListAPIView):
    """
    GET /api/products/{slug}/reviews/

    List approved reviews for a product.
    """

    serializer_class = ReviewSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        slug = self.kwargs["product_slug"]
        return (
            Review.objects.filter(
                product__slug=slug,
                product__is_active=True,
                is_approved=True,
            )
            .select_related("user")
            .order_by("-created_at")
        )


class ProductReviewCreateView(generics.CreateAPIView):
    """
    POST /api/products/{slug}/reviews/

    Submit a new review for a product.
    Per PRD §3.4: new reviews start with is_approved=False (moderation queue).
    One review per user per product.
    """

    serializer_class = ReviewCreateSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        slug = self.kwargs["product_slug"]

        try:
            product = Product.objects.get(slug=slug, is_active=True)
        except Product.DoesNotExist:
            return Response(
                {"error": {"code": "not_found", "detail": "Prodotto non trovato."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check for existing review
        if Review.objects.filter(user=request.user, product=product).exists():
            return Response(
                {
                    "error": {
                        "code": "duplicate_review",
                        "detail": "Hai già recensito questo prodotto.",
                    }
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            user=request.user,
            product=product,
            is_approved=False,  # Enters moderation queue
        )

        return Response(
            {
                "message": "Grazie per la tua recensione! Sarà pubblicata dopo la moderazione.",
                "review": ReviewSerializer(serializer.instance).data,
            },
            status=status.HTTP_201_CREATED,
        )
