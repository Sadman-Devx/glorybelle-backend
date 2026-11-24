from django.contrib import admin

from .models import StaffRoleChange


@admin.register(StaffRoleChange)
class StaffRoleChangeAdmin(admin.ModelAdmin):
    list_display = (
        "target_email",
        "from_role",
        "to_role",
        "changed_by_email",
        "created_at",
    )
    list_filter = ("from_role", "to_role", "created_at")
    search_fields = ("target_email", "changed_by_email")
    readonly_fields = (
        "target_user",
        "target_email",
        "changed_by",
        "changed_by_email",
        "from_role",
        "to_role",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
