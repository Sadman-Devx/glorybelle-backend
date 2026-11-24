import smtplib
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, generics, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import AdminJWTAuthentication
from .models import StaffRoleChange
from .pagination import AdminPagination
from .permissions import IsSuperuser
from .staff_roles import assign_staff_role
from .staff_serializers import (
    AdminStaffInviteSerializer,
    AdminStaffRoleUpdateSerializer,
    AdminStaffUserSerializer,
    StaffPasswordLinkResponseSerializer,
    StaffRoleChangeSerializer,
)
User = get_user_model()


class StaffEmailDeliveryError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Non è stato possibile inviare l'email. Riprova più tardi."
    default_code = "email_delivery_failed"


def send_password_setup_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend_url = settings.FRONTEND_URL.rstrip("/")
    reset_url = f"{frontend_url}/reset-password?uid={uid}&token={token}"
    message = (
        f"Ciao {user.first_name or user.email},\n\n"
        "Il tuo accesso allo spazio amministrativo GLORYBELLE è pronto. "
        "Imposta la password dal link seguente:\n"
        f"{reset_url}\n\n"
        "Se non hai richiesto questo invito, puoi ignorare questa email."
    )
    try:
        sent = send_mail(
            "GLORYBELLE — Imposta la tua password",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException) as exc:
        raise StaffEmailDeliveryError() from exc
    if sent != 1:
        raise StaffEmailDeliveryError()


class AdminStaffListCreateView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]
    serializer_class = AdminStaffUserSerializer
    pagination_class = AdminPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active", "is_superuser"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "first_name", "last_name", "date_joined"]
    ordering = ["email", "pk"]

    def get_queryset(self):
        return User.objects.filter(is_staff=True).prefetch_related("groups")

    @extend_schema(
        request=AdminStaffInviteSerializer,
        responses={201: AdminStaffUserSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = AdminStaffInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=f"staff-{uuid.uuid4().hex}",
                email=values["email"],
                first_name=values.get("first_name", ""),
                last_name=values.get("last_name", ""),
                is_staff=True,
                is_active=True,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            assign_staff_role(user, values["role"], request.user)
        send_password_setup_email(user)
        return Response(
            AdminStaffUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class AdminStaffRoleUpdateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]

    @extend_schema(
        request=AdminStaffRoleUpdateSerializer,
        responses=AdminStaffUserSerializer,
    )
    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_staff=True)
        if user.is_superuser:
            raise ValidationError({"detail": "Il ruolo di un superuser non è modificabile."})
        serializer = AdminStaffRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            assign_staff_role(user, serializer.validated_data["role"], request.user)
        return Response(AdminStaffUserSerializer(user).data)


class AdminStaffDeactivateView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]
    serializer_class = AdminStaffUserSerializer

    @extend_schema(responses=AdminStaffUserSerializer)
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_staff=True)
        if user.is_superuser:
            raise ValidationError({"detail": "Non è possibile disattivare un superuser."})
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "Non puoi disattivare il tuo stesso account."})
        if user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
        return Response(AdminStaffUserSerializer(user).data)


class AdminStaffPasswordLinkView(APIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]
    serializer_class = StaffPasswordLinkResponseSerializer

    @extend_schema(responses={202: StaffPasswordLinkResponseSerializer})
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_staff=True)
        if not user.is_active:
            raise ValidationError(
                {"detail": "Riattiva l'utente prima di inviare un link password."}
            )
        send_password_setup_email(user)
        return Response(
            {"detail": f"Link password inviato a {user.email}."},
            status=status.HTTP_202_ACCEPTED,
        )


class AdminStaffRoleAuditListView(generics.ListAPIView):
    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsSuperuser]
    serializer_class = StaffRoleChangeSerializer
    pagination_class = AdminPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["target_email", "changed_by_email", "from_role", "to_role"]
    ordering_fields = ["created_at", "target_email", "to_role"]
    ordering = ["-created_at", "-pk"]
    queryset = StaffRoleChange.objects.all()
