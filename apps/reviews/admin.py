"""
GLORYBELLE — Review Admin.

Per PRD §3.4: moderation queue with is_approved filter and bulk approve action.
"""
from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "user",
        "rating",
        "title",
        "is_approved",
        "created_at",
    )
    list_filter = ("is_approved", "rating", "created_at")
    search_fields = ("title", "body", "user__username", "product__name")
    list_editable = ("is_approved",)
    readonly_fields = ("user", "product", "rating", "title", "body", "created_at")
    actions = ["approve_reviews", "reject_reviews"]

    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} recensione/i approvata/e.")

    approve_reviews.short_description = "Approva le recensioni selezionate"

    def reject_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} recensione/i rifiutata/e.")

    reject_reviews.short_description = "Rifiuta le recensioni selezionate"
