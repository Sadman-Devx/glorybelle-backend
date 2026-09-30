"""
GLORYBELLE — Review Serializers.
"""
from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Public review — only shows approved reviews."""

    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(
        source="user.first_name", read_only=True
    )

    class Meta:
        model = Review
        fields = [
            "id",
            "username",
            "first_name",
            "rating",
            "title",
            "body",
            "created_at",
        ]
        read_only_fields = fields


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Input for creating a new review."""

    class Meta:
        model = Review
        fields = ["rating", "title", "body"]

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError(
                "La valutazione deve essere tra 1 e 5."
            )
        return value
