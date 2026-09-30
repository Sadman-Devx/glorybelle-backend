"""
GLORYBELLE — Account Views.

Thin HTTP adapter — registration, profile, addresses.
"""
from rest_framework import generics, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from core.permissions import IsOwner

from .models import Address, CustomerProfile
from .serializers import AddressSerializer, CustomerProfileSerializer, RegisterSerializer


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
