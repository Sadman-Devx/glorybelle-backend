"""
GLORYBELLE — Account Admin.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Address, CustomerProfile


class CustomerProfileInline(admin.StackedInline):
    model = CustomerProfile
    can_delete = False
    verbose_name_plural = "Profilo"


class UserAdmin(BaseUserAdmin):
    inlines = [CustomerProfileInline]


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
