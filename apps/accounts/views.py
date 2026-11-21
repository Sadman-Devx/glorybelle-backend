"""
GLORYBELLE — Account Views.

Thin HTTP adapter — registration, profile, addresses, auth.

P1 fix #10: adds logout (JWT refresh token blacklist) and password-reset
request endpoints. The actual password reset confirmation + set-new-password
flow is implemented as a two-step sequence (request → confirm) per OWASP best
practice.
"""
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.permissions import IsOwner

from .models import Address, CustomerProfile
from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    """
    POST /api/accounts/register/

    Create a new user account. Returns JWT tokens.
    """

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate JWT tokens
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


class LogoutView(APIView):
    """
    POST /api/accounts/logout/

    Blacklist the refresh token so it can no longer be used to mint new access tokens.
    Requires the refresh token in the request body.

    Per rule.md: "Avoid weakening password/auth requirements temporarily."
    Logout is permanent — once blacklisted, the refresh token is dead.

    Request body: {"refresh": "<refresh_token>"}
    Returns: 204 No Content on success
    """

    permission_classes = [IsAuthenticated]

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
    """
    POST /api/accounts/password/reset/

    Request a password reset email. Sends a token + uid to the user's email
    if an account with that email exists. Always returns 202 (never reveals
    whether the email exists in our database — anti-enumeration).

    Request body: {"email": "user@example.com"}
    Returns: 202 Accepted (always)
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            # Don't reveal whether the email exists — return success silently
            return Response(
                {"detail": "Se l'email esiste, riceverai un link di reset."},
                status=status.HTTP_202_ACCEPTED,
            )

        # Generate one-time token + uid
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        # Build reset URL — frontend route that handles the reset form
        reset_url = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

        # Send email — uses console backend in dev (EMAIL_BACKEND), SendGrid in prod
        context = {
            "user": user,
            "reset_url": reset_url,
            "site_name": "GLORYBELLE",
        }
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
    """
    POST /api/accounts/password/reset/confirm/

    Set a new password using the uid + token from the reset email.

    Request body:
        {"uid": "<uid>", "token": "<token>", "new_password": "..."}
    Returns: 200 OK on success
    """

    permission_classes = [AllowAny]

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

        # Invalidate all outstanding refresh tokens for this user (security best practice)
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
    """
    GET  /api/accounts/me/  → current user profile
    PATCH /api/accounts/me/ → update profile
    """

    serializer_class = CustomerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = CustomerProfile.objects.get_or_create(user=self.request.user)
        return profile


class AddressViewSet(viewsets.ModelViewSet):
    """
    CRUD for customer addresses. Owner-scoped.

    GET    /api/accounts/addresses/      → list user's addresses
    POST   /api/accounts/addresses/      → create new address
    GET    /api/accounts/addresses/{id}/  → retrieve
    PATCH  /api/accounts/addresses/{id}/  → update
    DELETE /api/accounts/addresses/{id}/  → delete
    """

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)
