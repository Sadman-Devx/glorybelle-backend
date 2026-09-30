"""
GLORYBELLE — Account URL Configuration.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import AddressViewSet, MeView, RegisterView

router = DefaultRouter()
router.register(r"accounts/addresses", AddressViewSet, basename="address")

urlpatterns = [
    # Auth
    path("accounts/register/", RegisterView.as_view(), name="register"),
    path("accounts/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("accounts/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Profile
    path("accounts/me/", MeView.as_view(), name="me"),
    # Addresses (via router)
    path("", include(router.urls)),
]
