"""
GLORYBELLE — Newsletter Serializers.
"""
from rest_framework import serializers


class NewsletterSubscribeSerializer(serializers.Serializer):
    """Input for newsletter subscription."""

    email = serializers.EmailField()


class NewsletterUnsubscribeSerializer(serializers.Serializer):
    """Input for newsletter unsubscription: the signed token from the e-mail link."""

    token = serializers.CharField(max_length=1000)
