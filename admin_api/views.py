from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.views import TokenRefreshView
from django_otp.plugins.otp_totp.models import TOTPDevice
from drf_spectacular.utils import extend_schema

from apps.catalog.models import Product, ProductVariant
from apps.orders.models import Order
from core.throttling import AnonRateThrottle

from .authentication import AdminJWTAuthentication
from .pagination import AdminPagination
from .permissions import IsAdminRole, IsSuperuser
from .serializers import (
    AdminHistorySerializer,
    AdminLoginSerializer,
    AdminMfaChallengeSerializer,
    AdminMfaVerifyResponseSerializer,
    AdminMfaVerifySerializer,
    AdminMeSerializer,
    AdminRefreshToken,
    AdminTokenRefreshSerializer,
    GENERIC_LOGIN_ERROR,
    admin_role,
)
from .security import (
    admin_totp_device,
    admin_totp_provisioning_details,
    clear_admin_login_failures,
    consume_admin_mfa_challenge,
    create_admin_auth_session,
    find_admin_mfa_challenge,
    is_admin_login_locked,
    issue_admin_mfa_challenge,
    record_admin_login_failure,
    replace_admin_recovery_codes,
    revoke_admin_session,
    revoke_user_admin_sessions,
    verify_admin_mfa_code,
)
from .throttling import AdminLoginRateThrottle


class AdminLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AdminLoginRateThrottle]
    serializer_class = AdminLoginSerializer

    @extend_schema(
        request=AdminLoginSerializer,
        responses={200: AdminMfaChallengeSerializer},
    )
    def post(self, request):
        identifier = (
            request.data.get("email", "")
            if isinstance(request.data, Mapping)
            else ""
        )
        if is_admin_login_locked(identifier):
            return Response(
                {"error": {"code": "authentication_failed", "detail": GENERIC_LOGIN_ERROR}},
                status=401,
            )
        serializer = self.serializer_class(
            data=request.data,
            context={"request": request},
        )
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            record_admin_login_failure(identifier)
            return Response(
                {
                    "error": {
                        "code": "authentication_failed",
                        "detail": GENERIC_LOGIN_ERROR,
                    }
                },
                status=401,
            )
        user = serializer.validated_data["user"]
        device = admin_totp_device(user, confirmed=True)
        if device is None:
            device = admin_totp_device(user, confirmed=False)
            if device is None:
                device = TOTPDevice.objects.create(
                    user=user,
                    name="admin-totp",
                    confirmed=False,
                )
            challenge = issue_admin_mfa_challenge(user, "enroll")
            return Response(
                {
                    "mfa_required": True,
                    "purpose": "enroll",
                    "challenge": challenge,
                    **admin_totp_provisioning_details(device),
                }
            )

        challenge = issue_admin_mfa_challenge(user, "verify")
        return Response(
            {
                "mfa_required": True,
                "purpose": "verify",
                "challenge": challenge,
            }
        )


class AdminMfaVerifyView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AdminLoginRateThrottle]
    serializer_class = AdminMfaVerifySerializer

    @extend_schema(
        request=AdminMfaVerifySerializer,
        responses={200: AdminMfaVerifyResponseSerializer},
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_challenge = serializer.validated_data["challenge"]
        code = serializer.validated_data["code"]

        with transaction.atomic():
            challenge = find_admin_mfa_challenge(raw_challenge, lock=True)
            if challenge is None or is_admin_login_locked(
                challenge.user.email or challenge.user.get_username()
            ):
                return Response(
                    {"detail": "Codice non valido o scaduto."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            user = get_user_model().objects.select_for_update().get(pk=challenge.user_id)
            if (
                not user.is_active
                or not user.is_staff
                or admin_role(user) is None
            ):
                consume_admin_mfa_challenge(challenge)
                return Response(
                    {"detail": "Codice non valido o scaduto."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            device = admin_totp_device(user, confirmed=(challenge.purpose == "verify"))
            valid_code = False
            if device is not None:
                valid_code = (
                    bool(
                        len(code.strip()) == device.digits
                        and code.strip().isdigit()
                        and device.verify_token(code.strip())
                    )
                    if challenge.purpose == "enroll"
                    else verify_admin_mfa_code(user, code) is not None
                )
            if not valid_code:
                record_admin_login_failure(user.email or user.get_username())
                return Response(
                    {"detail": "Codice non valido o scaduto."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if challenge.purpose == "enroll":
                device.confirmed = True
                device.save(update_fields=["confirmed"])
                recovery_codes = replace_admin_recovery_codes(user)
            else:
                recovery_codes = None

            consume_admin_mfa_challenge(challenge)
            clear_admin_login_failures(user.email or user.get_username())
            auth_session = create_admin_auth_session(user)
            refresh = AdminRefreshToken.for_user(user, auth_session.session_id)
            token_data = {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "mfa_required": False,
            }
            if recovery_codes is not None:
                token_data["recovery_codes"] = recovery_codes
            return Response(token_data)


class AdminLogoutView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        revoke_admin_session(request.auth.get("admin_session_id"), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminLogoutEverywhereView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        revoke_user_admin_sessions(request.user, "logout_everywhere")
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminTokenRefreshView(TokenRefreshView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    serializer_class = AdminTokenRefreshSerializer


class AdminMeView(generics.RetrieveAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAdminRole]
    serializer_class = AdminMeSerializer

    def get_object(self):
        return self.request.user


class AdminAuditListView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["history_type", "history_user__id"]
    search_fields = [
        "history_change_reason",
        "history_user__username",
        "history_user__email",
    ]
    ordering_fields = ["history_date", "history_id", "id", "history_type"]
    ordering = ["-history_date", "-history_id"]
    serializer_class = AdminHistorySerializer
    histories = {
        "order": (Order, "order"),
        "product": (Product, "product"),
        "productvariant": (ProductVariant, "productvariant"),
        "product_variant": (ProductVariant, "productvariant"),
    }

    def get_history_model(self):
        model_name = self.request.query_params.get("model", "").strip().casefold()
        try:
            return self.histories[model_name]
        except KeyError as exc:
            raise ValidationError(
                {"model": "Scegliere order, product o productvariant."}
            ) from exc

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            self.model_name = "order"
            return Order.history.none()
        model, model_name = self.get_history_model()
        queryset = model.history.all()
        object_id = self.request.query_params.get("object_id")
        if object_id is not None:
            try:
                parsed_object_id = int(object_id)
            except ValueError as exc:
                raise ValidationError(
                    {"object_id": "L'identificativo deve essere numerico."}
                ) from exc
            if parsed_object_id < 0:
                raise ValidationError(
                    {"object_id": "L'identificativo deve essere numerico."}
                )
            queryset = queryset.filter(id=parsed_object_id)
        self.model_name = model_name
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["model_name"] = getattr(self, "model_name", "order")
        return context

