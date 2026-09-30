"""
GLORYBELLE — Newsletter Serializers.
"""
from rest_framework import serializers


class NewsletterSubscribeSerializer(serializers.Serializer):
    """Input for newsletter subscription."""

    email = serializers.EmailField()


class NewsletterUnsubscribeSerializer(serializers.Serializer):
    """Input for newsletter unsubscription."""

    email = serializers.EmailField()
