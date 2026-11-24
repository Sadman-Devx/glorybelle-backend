from django.utils.html import strip_tags
from rest_framework import serializers

from .models import Enquiry


class EnquiryCreateSerializer(serializers.ModelSerializer):
    website = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        max_length=254,
    )

    class Meta:
        model = Enquiry
        fields = (
            "name",
            "email",
            "topic",
            "message",
            "atelier_type",
            "website",
        )

    def validate_message(self, value):
        plain_text = strip_tags(value).strip()
        if not plain_text:
            raise serializers.ValidationError(
                "Il messaggio deve contenere del testo."
            )
        return plain_text

    def validate(self, attrs):
        if attrs.get("atelier_type") and attrs["topic"] != "atelier":
            raise serializers.ValidationError(
                {"atelier_type": "Questo campo è disponibile solo per le richieste Atelier."}
            )
        return attrs
