"""
GLORYBELLE — Account Admin.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

from admin_api.serializers import admin_role
from admin_api.staff_roles import record_staff_role_change
from .models import Address, CustomerProfile


class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    can_delete = False
    verbose_name_plural = _("Profilo")


class UserAdmin(BaseUserAdmin):
    inlines = [CustomerProfileInline]

    def save_model(self, request, obj, form, change):
        request._glorybelle_role_before = (
            admin_role(User.objects.get(pk=obj.pk)) if change else None
        )
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        old_role = getattr(request, "_glorybelle_role_before", None)
        new_role = admin_role(form.instance)
        record_staff_role_change(form.instance, request.user, old_role, new_role)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "city",
        "province",
        "postal_code",
        "is_default",
        "user",
    )
    list_filter = ("province", "is_default")
    search_fields = ("first_name", "last_name", "city", "user__username")


# Re-register User with profile inline
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
