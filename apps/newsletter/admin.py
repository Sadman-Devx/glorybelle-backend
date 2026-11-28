"""
GLORYBELLE — Newsletter Admin.
"""
from django.contrib import admin

from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "is_active",
        "is_confirmed",
        "subscribed_at",
        "unsubscribed_at",
    )
    list_filter = ("is_active", "is_confirmed")
    search_fields = ("email",)
    readonly_fields = ("subscribed_at", "unsubscribed_at")
