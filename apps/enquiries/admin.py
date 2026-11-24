from django.contrib import admin

from .models import Enquiry, EnquiryNote


class EnquiryNoteInline(admin.TabularInline):
    model = EnquiryNote
    extra = 0
    can_delete = False
    readonly_fields = ("author", "body", "created_at")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "topic", "status", "assigned_to", "created_at")
    list_filter = ("topic", "status", "atelier_type", "created_at")
    search_fields = ("name", "email", "message")
    readonly_fields = ("created_at", "updated_at")
    inlines = (EnquiryNoteInline,)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EnquiryNote)
class EnquiryNoteAdmin(admin.ModelAdmin):
    list_display = ("enquiry", "author", "created_at")
    search_fields = ("body", "enquiry__name", "enquiry__email")
    readonly_fields = ("enquiry", "author", "body", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
