"""
GLORYBELLE — Newsletter Views.

Public endpoints — no authentication required.
"""
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NewsletterSubscriber
from .serializers import NewsletterSubscribeSerializer, NewsletterUnsubscribeSerializer


class NewsletterSubscribeView(APIView):
    """
    POST /api/newsletter/subscribe/

    Subscribe to the newsletter. Handles duplicate emails gracefully:
    if already subscribed and active, returns success without error.
    If previously unsubscribed, re-activates.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = NewsletterSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        subscriber, created = NewsletterSubscriber.objects.get_or_create(
            email=email,
            defaults={"is_active": True},
        )

        if not created and not subscriber.is_active:
            # Re-subscribe
            subscriber.is_active = True
            subscriber.unsubscribed_at = None
            subscriber.save(update_fields=["is_active", "unsubscribed_at"])

        return Response(
            {"message": "Iscrizione confermata! Grazie per aver scelto GLORYBELLE."},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class NewsletterUnsubscribeView(APIView):
    """
    POST /api/newsletter/unsubscribe/

    Unsubscribe from the newsletter. Soft-delete (GDPR).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = NewsletterUnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        try:
            subscriber = NewsletterSubscriber.objects.get(email=email)
            subscriber.is_active = False
            subscriber.unsubscribed_at = timezone.now()
            subscriber.save(update_fields=["is_active", "unsubscribed_at"])
        except NewsletterSubscriber.DoesNotExist:
            pass  # Don't reveal whether the email was subscribed

        return Response(
            {"message": "Iscrizione annullata con successo."},
            status=status.HTTP_200_OK,
        )
