"""
GLORYBELLE — Account Serializers.

P1 fix #10: PasswordReset serializers added.
New: birth_date field added to RegisterSerializer (PRD §2.2 + project owner request).
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Address, CustomerProfile


def validate_age_from_birth_date(value):
    """Shared rule: 13 <= age <= 120 (registration AND profile updates)."""
    from datetime import date

    today = date.today()
    age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
    if age < 13:
        raise serializers.ValidationError("Devi avere almeno 13 anni per registrarti.")
    if age > 120:
        raise serializers.ValidationError("Data di nascita non valida.")
    return value


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

    def validate_date_of_birth(self, value):
        if value is not None:
            validate_age_from_birth_date(value)
        return value


class RegisterSerializer(serializers.Serializer):
    """
    User registration.

    Creates User + CustomerProfile in one step.
    Returns JWT tokens on success.

    New: birth_date is required at registration (project owner request).
    Used to personalize the customer experience and for first-purchase
    eligibility tracking.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=30, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")
    phone = serializers.CharField(max_length=20, required=False, default="")
    # NEW — birth_date required at registration
    birth_date = serializers.DateField(
        required=True,
        help_text="Data di nascita — usata per personalizzare l'esperienza.",
    )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Questo username è già in uso.")
        return value

    def validate_email(self, value):
        # Emails are case-insensitive: A@x.com and a@x.com are the same mailbox.
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Questa email è già registrata.")
        return value

    def validate_birth_date(self, value):
        """Must be at least 13 years old (COPPA-equivalent)."""
        return validate_age_from_birth_date(value)

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Le password non corrispondono."}
            )
        return data

    def create(self, validated_data):
        phone = validated_data.pop("phone", "")
        birth_date = validated_data.pop("birth_date")
        validated_data.pop("password_confirm")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        CustomerProfile.objects.create(
            user=user,
            phone=phone,
            date_of_birth=birth_date,
        )
        return user


class PasswordResetSerializer(serializers.Serializer):
    """Input for POST /api/accounts/password/reset/."""

    email = serializers.EmailField()


class LogoutSerializer(serializers.Serializer):
    """Input for POST /api/accounts/logout/."""

    refresh = serializers.CharField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Input for POST /api/accounts/password/reset/confirm/."""

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


class FirstPurchaseDiscountSerializer(serializers.Serializer):
    """Response serializer for GET /api/accounts/first-purchase-discount/."""

    eligible = serializers.BooleanField()
    percent = serializers.DecimalField(max_digits=5, decimal_places=2)
    message = serializers.CharField(allow_blank=True)


class EmailOrUsernameTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    JWT login that accepts EITHER ``email`` or ``username`` plus ``password``.

    The storefront login form asks for an email address, while SimpleJWT's
    default serializer only understands ``username``. Email matching is
    case-insensitive. Failure is always the generic SimpleJWT 401 so the
    endpoint does not reveal whether an email exists.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field].required = False
        self.fields["email"] = serializers.CharField(required=False, write_only=True)

    def validate(self, attrs):
        username = (attrs.get(self.username_field) or "").strip()
        email = (attrs.get("email") or "").strip()
        password = attrs.get("password")

        if not username and not email:
            raise serializers.ValidationError(
                {"email": "Inserisci email o username."}
            )

        if not username:
            candidates = list(
                User.objects.filter(email__iexact=email, is_active=True).order_by("id")
            )
            # Pick the account whose password matches (handles legacy accounts
            # that share an email address differing only by case).
            matched = next((u for u in candidates if u.check_password(password)), None)
            chosen = matched or (candidates[0] if candidates else None)
            # Unknown email -> keep a value so SimpleJWT raises its generic 401.
            username = chosen.get_username() if chosen else email

        return super().validate(
            {self.username_field: username, "password": password}
        )
