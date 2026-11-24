from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import StaffRoleChange
from .serializers import admin_role

User = get_user_model()
STAFF_ROLE_CHOICES = (("manager", "Manager"), ("viewer", "Viewer"))


class AdminStaffUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "name",
            "role",
            "is_active",
            "is_superuser",
            "date_joined",
        )
        read_only_fields = fields

    def get_name(self, user) -> str:
        return " ".join(part for part in (user.first_name, user.last_name) if part)

    def get_role(self, user) -> str | None:
        return admin_role(user)


class AdminStaffInviteSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "Esiste già un account con questo indirizzo email."
            )
        return email


class AdminStaffRoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=STAFF_ROLE_CHOICES)


class StaffRoleChangeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRoleChange
        fields = (
            "id",
            "target_email",
            "from_role",
            "to_role",
            "changed_by_email",
            "created_at",
        )
        read_only_fields = fields


class StaffPasswordLinkResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
