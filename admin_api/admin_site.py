from django.core.exceptions import ValidationError as DjangoValidationError
from django_otp.admin import OTPAdminAuthenticationForm, OTPAdminSite
from unfold.sites import UnfoldAdminSite

from .security import (
    clear_admin_login_failures,
    is_admin_login_locked,
    record_admin_login_failure,
)


class LockedOTPAdminAuthenticationForm(OTPAdminAuthenticationForm):
    def clean(self):
        identifier = self.data.get(self.username_field, "")
        if is_admin_login_locked(identifier):
            raise DjangoValidationError("Credenziali non valide.")
        try:
            result = super().clean()
        except DjangoValidationError:
            record_admin_login_failure(identifier)
            raise
        clear_admin_login_failures(identifier)
        return result


class OTPUnfoldAdminSite(OTPAdminSite, UnfoldAdminSite):
    login_form = LockedOTPAdminAuthenticationForm

    def has_permission(self, request):
        return (
            super().has_permission(request)
            and request.user.is_superuser
            and request.user.is_verified()
        )
