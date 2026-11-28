"""
GLORYBELLE — Newsletter Views.

Public endpoints — no authentication required.
"""
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import NewsletterSubscriber
from .serializers import NewsletterSubscribeSerializer, NewsletterUnsubscribeSerializer
from .tokens import read_unsubscribe_token


class NewsletterSubscribeView(APIView):
    """
    POST /api/newsletter/subscribe/

    Subscribe to the newsletter. Handles duplicate emails gracefully:
    if already subscribed and active, returns success without error.
    If previously unsubscribed, re-activates.
    """

    permission_classes = [AllowAny]
    serializer_class = NewsletterSubscribeSerializer

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
    POST /api/newsletter/unsubscribe/   body: {"token": "<signed token from the e-mail link>"}

    Unsubscribe from the newsletter. Soft-delete (GDPR). The token is signed, so only the
    link we put in a newsletter e-mail can unsubscribe an address — a bare e-mail address
    is NOT accepted any more (anyone could otherwise unsubscribe anyone).
    """

    permission_classes = [AllowAny]
    serializer_class = NewsletterUnsubscribeSerializer

    def post(self, request):
        serializer = NewsletterUnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = read_unsubscribe_token(serializer.validated_data["token"])
        if email is None:
            raise serializers.ValidationError(
                {"token": "Link di annullamento non valido o danneggiato."}
            )
        NewsletterSubscriber.objects.filter(email__iexact=email, is_active=True).update(
            is_active=False, unsubscribed_at=timezone.now()
        )
        # Same answer whether or not the address was still subscribed (idempotent)
        return Response(
            {"message": "Iscrizione annullata con successo."},
            status=status.HTTP_200_OK,
        )
