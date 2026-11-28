"""
GLORYBELLE — Account Views.

P1 fix #10: logout, password-reset endpoints.
New: GET /api/accounts/first-purchase-discount/ — eligibility check for the
first-purchase 10% discount. Used by the frontend to show the offer to guests
who haven't registered yet.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from core.permissions import IsOwner
from core.throttling import ScopedRateThrottle

from .models import Address, CustomerProfile
from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    EmailOrUsernameTokenObtainPairSerializer,
    FirstPurchaseDiscountSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    """POST /api/accounts/register/"""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                },
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/accounts/login/  — body: {email | username, password}"""

    serializer_class = EmailOrUsernameTokenObtainPairSerializer
    # Password-guessing brake (the global anon limit is 1000/hour, far too loose).
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class LogoutView(APIView):
    """POST /api/accounts/logout/"""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Il token di refresh è obbligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            logger.warning("Logout failed for user %s: %s", request.user.id, e)
            return Response(
                {"error": "Token non valido o già revocato."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(APIView):
    """POST /api/accounts/password/reset/"""

    permission_classes = [AllowAny]
    serializer_class = PasswordResetSerializer

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        # .filter(): accounts created before email uniqueness became case-insensitive
        # can share an address — .get() raised MultipleObjectsReturned (HTTP 500).
        for user in User.objects.filter(email__iexact=email, is_active=True):
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

            try:
                plain_message = (
                    f"Hai richiesto di reimpostare la password del tuo account GLORYBELLE.\n\n"
                    f"Clicca sul seguente link per reimpostarla:\n{reset_url}\n\n"
                    f"Se non hai richiesto questo reset, ignora questa email.\n\n"
                    f"Team GLORYBELLE"
                )
                send_mail(
                    subject="GLORYBELLE — Reset della password",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                logger.info("Password reset email sent to %s", user.email)
            except Exception as e:
                logger.error("Failed to send password reset email: %s", e)

        return Response(
            {"detail": "Se l'email esiste, riceverai un link di reset."},
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(APIView):
    """POST /api/accounts/password/reset/confirm/"""

    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = serializer.validated_data["user"]
        except Exception:
            return Response(
                {"error": "Link non valido o scaduto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_password = serializer.validated_data["new_password"]
        user.set_password(new_password)
        user.save(update_fields=["password"])

        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        from rest_framework_simplejwt.tokens import RefreshToken
        try:
            outstanding = OutstandingToken.objects.filter(user=user)
            for token in outstanding:
                try:
                    RefreshToken(token.token).blacklist()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Could not blacklist outstanding tokens for user %s: %s", user.id, e)

        logger.info("Password reset successful for user %s", user.id)
        return Response(
            {"detail": "Password reimpostata con successo."},
            status=status.HTTP_200_OK,
        )


class MeView(generics.RetrieveUpdateAPIView):
    """GET  /api/accounts/me/  → profile
    PATCH /api/accounts/me/ → update"""

    serializer_class = CustomerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        return profile


class FirstPurchaseDiscountView(APIView):
    """
    GET /api/accounts/first-purchase-discount/

    Returns whether the current user (or a guest, by default) is eligible
    for the first-purchase 10% discount. Used by the frontend to show
    the offer banner in the cart drawer.

    Response:
        {
            "eligible": true,
            "percent": "10.00",
            "message": "Registra un account e ottieni il 10% di sconto sul primo ordine."
        }

    For authenticated users: returns true if they have no prior completed orders.
    For guests: always returns true (they would need to register to claim).
    """

    permission_classes = [AllowAny]
    serializer_class = FirstPurchaseDiscountSerializer

    def get(self, request):
        # Import here to avoid circular import
        from apps.orders.services import is_first_purchase

        if request.user.is_authenticated:
            eligible = is_first_purchase(request.user)
            if eligible:
                message = (
                    "Hai diritto al 10% di sconto su un prodotto del tuo primo ordine: "
                    "lo sconto viene applicato automaticamente."
                )
            else:
                message = ""
        else:
            eligible = True
            message = (
                "Registra un account e ottieni il 10% di sconto su un prodotto "
                "del tuo primo ordine."
            )

        percent = getattr(
            settings,
            "FIRST_PURCHASE_DISCOUNT_PERCENT",
            Decimal("10.00"),
        )

        serializer = FirstPurchaseDiscountSerializer(
            data={
                "eligible": eligible,
                "percent": str(percent),
                "message": message,
            }
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class AddressViewSet(viewsets.ModelViewSet):
    """CRUD for customer addresses."""

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    queryset = Address.objects.none()

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)
