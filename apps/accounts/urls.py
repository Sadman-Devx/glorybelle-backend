"""
GLORYBELLE — Account URL Configuration.

P1 fix #10: adds logout, password-reset, password-reset-confirm endpoints.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AddressViewSet,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetView,
    RegisterView,
)

router = DefaultRouter()
router.register(r"accounts/addresses", AddressViewSet, basename="address")

urlpatterns = [
    # Auth
    path("accounts/register/", RegisterView.as_view(), name="register"),
    path("accounts/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accounts/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # P1 fix #10 — logout + password reset
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path(
        "accounts/password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # Profile
    path("accounts/me/", MeView.as_view(), name="me"),
    # Addresses (via router)
    path("", include(router.urls)),
]
