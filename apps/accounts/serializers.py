"""
GLORYBELLE — Account Serializers.

P1 fix #10: adds PasswordResetSerializer and PasswordResetConfirmSerializer
for the new /api/accounts/password/reset/ and /api/accounts/password/reset/confirm/
endpoints.
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import Address, CustomerProfile


class CustomerProfileSerializer(serializers.ModelSerializer):
    """Read/update customer profile."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "date_of_birth",
            "created_at",
        ]
        read_only_fields = ["id", "username", "email", "first_name", "last_name", "created_at"]


class RegisterSerializer(serializers.Serializer):
    """
    User registration.

    Creates User + CustomerProfile in one step.
    Returns JWT tokens on success.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=30, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")
    phone = serializers.CharField(max_length=20, required=False, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Questo username è già in uso.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Questa email è già registrata.")
        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Le password non corrispondono."}
            )
        return data

    def create(self, validated_data):
        phone = validated_data.pop("phone", "")
        validated_data.pop("password_confirm")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        CustomerProfile.objects.create(user=user, phone=phone)
        return user


# =============================================================================
# Password Reset (P1 fix #10)
# =============================================================================

class PasswordResetSerializer(serializers.Serializer):
    """Input for POST /api/accounts/password/reset/."""

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Input for POST /api/accounts/password/reset/confirm/.

    Validates the uid + token pair from the reset email, then sets the
    new password. The user is attached to validated_data so the view can
    call user.set_password().
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Le password non corrispondono."}
            )

        try:
            uid = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Link non valido."})

        if not default_token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError({"token": "Token non valido o scaduto."})

        data["user"] = user
        return data


# =============================================================================
# Addresses
# =============================================================================

class AddressSerializer(serializers.ModelSerializer):
    """Customer address CRUD."""

    class Meta:
        model = Address
        fields = [
            "id",
            "first_name",
            "last_name",
            "line1",
            "line2",
            "city",
            "province",
            "postal_code",
            "country",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
