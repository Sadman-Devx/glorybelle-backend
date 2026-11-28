"""
GLORYBELLE — Newsletter Views.

Public endpoints — no authentication required.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.throttling import ScopedRateThrottle

from .models import NewsletterSubscriber
from .serializers import (
    NewsletterConfirmSerializer,
    NewsletterSubscribeSerializer,
    NewsletterUnsubscribeSerializer,
)
from .tasks import send_confirmation_email
from .tokens import (
    ConfirmationTokenExpired,
    read_confirmation_token,
    read_unsubscribe_token,
)


class NewsletterConfirmationExpired(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "Il link di conferma è scaduto. Iscriviti di nuovo per ricevere un link."
    default_code = "newsletter_confirmation_expired"


class NewsletterSubscribeView(APIView):
    """
    POST /api/newsletter/subscribe/

    Record a pending subscription and send one confirmation email per cooldown.
    The response deliberately does not reveal the address's current subscription state.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    serializer_class = NewsletterSubscribeSerializer
    throttle_scope = "newsletter_subscribe"

    def post(self, request):
        serializer = NewsletterSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        should_send_confirmation = False
        confirmation_nonce = None
        with transaction.atomic():
            subscriber, created = NewsletterSubscriber.objects.get_or_create(
                email=email,
                defaults={"is_active": True, "is_confirmed": False},
            )
            subscriber = NewsletterSubscriber.objects.select_for_update().get(
                pk=subscriber.pk
            )

            if not created and not subscriber.is_active:
                subscriber.is_active = True
                subscriber.is_confirmed = False
                subscriber.unsubscribed_at = None
                subscriber.confirmation_nonce = uuid.uuid4()

            cooldown = timedelta(
                minutes=settings.NEWSLETTER_CONFIRMATION_COOLDOWN_MINUTES
            )
            can_send = (
                subscriber.is_active
                and not subscriber.is_confirmed
                and (
                    subscriber.confirmation_sent_at is None
                    or subscriber.confirmation_sent_at <= timezone.now() - cooldown
                )
            )
            if can_send:
                subscriber.confirmation_sent_at = timezone.now()
                confirmation_nonce = str(subscriber.confirmation_nonce)
                should_send_confirmation = True

            subscriber.save(
                update_fields=[
                    "is_active",
                    "is_confirmed",
                    "unsubscribed_at",
                    "confirmation_nonce",
                    "confirmation_sent_at",
                ]
            )
            if should_send_confirmation:
                transaction.on_commit(
                    lambda: send_confirmation_email.delay(
                        subscriber.pk, confirmation_nonce
                    )
                )
        return Response(
            {
                "message": (
                    "Se l'indirizzo può essere iscritto, riceverai un'email con "
                    "le istruzioni per confermare."
                )
            },
            status=status.HTTP_202_ACCEPTED,
        )


class NewsletterConfirmView(APIView):
    """POST /api/newsletter/confirm/ with the signed opt-in token."""

    permission_classes = [AllowAny]
    serializer_class = NewsletterConfirmSerializer

    def post(self, request):
        serializer = NewsletterConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = read_confirmation_token(serializer.validated_data["token"])
        except ConfirmationTokenExpired as exc:
            raise NewsletterConfirmationExpired() from exc
        if payload is None:
            raise serializers.ValidationError(
                {"token": "Link di conferma non valido."}
            )

        with transaction.atomic():
            subscriber = (
                NewsletterSubscriber.objects.select_for_update()
                .filter(email__iexact=payload["email"], is_active=True)
                .first()
            )
            if (
                subscriber is None
                or str(subscriber.confirmation_nonce) != payload["nonce"]
            ):
                raise serializers.ValidationError(
                    {"token": "Link di conferma non valido."}
                )
            if not subscriber.is_confirmed:
                subscriber.is_confirmed = True
                subscriber.save(update_fields=["is_confirmed"])

        return Response(
            {"message": "Iscrizione alla newsletter confermata."},
            status=status.HTTP_200_OK,
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
            is_active=False,
            is_confirmed=False,
            confirmation_nonce=uuid.uuid4(),
            unsubscribed_at=timezone.now(),
        )
        # Same answer whether or not the address was still subscribed (idempotent)
        return Response(
            {"message": "Iscrizione annullata con successo."},
            status=status.HTTP_200_OK,
        )
