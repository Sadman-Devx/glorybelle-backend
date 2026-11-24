from datetime import timedelta

from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from .permissions import MANAGER_GROUP, VIEWER_GROUP

GENERIC_LOGIN_ERROR = "Credenziali non valide."

PERMISSIONS_BY_ROLE = {
    "manager": [
        "orders:read",
        "orders:write",
        "products:read",
        "products:write",
        "media:read",
        "media:write",
        "enquiries:read",
        "enquiries:write",
        "content:read",
        "content:write",
    ],
    "viewer": [
        "orders:read",
        "products:read",
        "media:read",
        "enquiries:read",
        "content:read",
    ],
}


def admin_role(user):
    if user.is_superuser:
        return "superuser"
    if user.groups.filter(name=MANAGER_GROUP).exists():
        return "manager"
    if user.groups.filter(name=VIEWER_GROUP).exists():
        return "viewer"
    return None


def admin_permissions(user):
    role = admin_role(user)
    if role == "superuser":
        return ["*"]
    return PERMISSIONS_BY_ROLE.get(role, [])


class AdminRefreshToken(RefreshToken):
    @classmethod
    def for_user(cls, user, session_id):
        token = super().for_user(user)
        token["admin_auth"] = True
        token["admin_session_id"] = str(session_id)
        return token

    @property
    def access_token(self):
        token = super().access_token
        token.set_exp(lifetime=timedelta(minutes=10))
        return token


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        User = get_user_model()
        email = attrs["email"].strip()
        password = attrs["password"]
        candidates = User.objects.filter(email__iexact=email)
        matching_email_count = candidates.count()
        user = candidates.first() if matching_email_count == 1 else None
        username = user.get_username() if user else email
        authenticated_user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )
        if (
            authenticated_user is None
            or not authenticated_user.is_active
            or not authenticated_user.is_staff
            or matching_email_count != 1
            or admin_role(authenticated_user) is None
        ):
            raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

        return {"user": authenticated_user}


class AdminMfaChallengeSerializer(serializers.Serializer):
    mfa_required = serializers.BooleanField()
    purpose = serializers.ChoiceField(choices=("enroll", "verify"))
    challenge = serializers.CharField()
    secret = serializers.CharField(required=False)
    provisioning_uri = serializers.URLField(required=False)


class AdminMfaVerifySerializer(serializers.Serializer):
    challenge = serializers.CharField(max_length=128)
    code = serializers.CharField(max_length=64)


class AdminMfaVerifyResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    mfa_required = serializers.BooleanField()
    recovery_codes = serializers.ListField(
        child=serializers.CharField(),
        required=False,
    )


class AdminTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = AdminRefreshToken

    def validate(self, attrs):
        try:
            refresh = self.token_class(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken("Token non valido o scaduto.") from exc
        if refresh.get("admin_auth") is not True:
            raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

        User = get_user_model()
        user = User.objects.filter(
            pk=refresh.get("user_id"),
            is_active=True,
            is_staff=True,
        ).first()
        if user is None or admin_role(user) is None:
            raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

        from .security import get_active_admin_session

        session_id = refresh.get("admin_session_id")
        if get_active_admin_session(user, session_id, touch=True) is None:
            raise AuthenticationFailed(GENERIC_LOGIN_ERROR)

        return super().validate(attrs)


class AdminMeSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_name(self, user) -> str:
        return user.get_full_name().strip() or user.get_username()

    def get_role(self, user) -> str | None:
        return admin_role(user)

    def get_permissions(self, user) -> list[str]:
        return admin_permissions(user)


class AdminHistorySerializer(serializers.Serializer):
    id = serializers.IntegerField(source="history_id")
    model = serializers.SerializerMethodField()
    object_id = serializers.CharField(source="id")
    timestamp = serializers.DateTimeField(source="history_date")
    action = serializers.CharField(source="history_type")
    actor_id = serializers.IntegerField(source="history_user_id", allow_null=True)
    actor_email = serializers.SerializerMethodField()
    reason = serializers.CharField(
        source="history_change_reason", allow_null=True, allow_blank=True
    )
    changed_fields = serializers.SerializerMethodField()

    def get_model(self, record) -> str:
        return self.context["model_name"]

    def get_actor_email(self, record) -> str | None:
        user = record.history_user
        return user.email if user else None

    def get_changed_fields(self, record) -> list[str]:
        previous = record.prev_record
        if previous is None:
            excluded = {"history_id", "history_date", "history_type", "history_user"}
            return [
                field.name
                for field in record._meta.fields
                if field.name not in excluded
                and not field.name.startswith("history_")
            ]
        return [
            change.field
            for change in record.diff_against(previous).changes
        ]
