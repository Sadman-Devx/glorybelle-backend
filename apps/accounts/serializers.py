"""
GLORYBELLE — Account Serializers.
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
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
