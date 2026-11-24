import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class StaffRoleChange(models.Model):
    ROLE_CHOICES = (
        ("superuser", _("Superuser")),
        ("manager", _("Manager")),
        ("viewer", _("Viewer")),
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_role_changes",
    )
    target_email = models.EmailField(_("Email utente"))
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_role_changes",
    )
    changed_by_email = models.EmailField(_("Email autore"), blank=True)
    from_role = models.CharField(_("Ruolo precedente"), max_length=20, blank=True)
    to_role = models.CharField(
        _("Nuovo ruolo"),
        max_length=20,
        blank=True,
        choices=ROLE_CHOICES,
    )
    created_at = models.DateTimeField(_("Data modifica"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Modifica ruolo staff")
        verbose_name_plural = _("Modifiche ruoli staff")

    def __str__(self):
        return f"{self.target_email}: {self.from_role or 'nessuno'} → {self.to_role or 'nessuno'}"


class AdminAuthSession(models.Model):
    REVOKE_REASONS = (
        ("logout", _("Disconnessione")),
        ("logout_everywhere", _("Disconnessione da tutti i dispositivi")),
        ("idle_timeout", _("Sessione inattiva")),
        ("password_changed", _("Password modificata")),
        ("role_changed", _("Ruolo modificato")),
        ("account_changed", _("Account modificato")),
    )

    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_auth_sessions",
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_activity = models.DateTimeField(default=timezone.now, db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True, db_index=True)
    revoke_reason = models.CharField(max_length=32, choices=REVOKE_REASONS, blank=True)

    class Meta:
        indexes = [models.Index(fields=("user", "revoked_at"))]


class AdminMfaChallenge(models.Model):
    PURPOSES = (
        ("verify", _("Verifica del secondo fattore")),
        ("enroll", _("Registrazione del secondo fattore")),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_mfa_challenges",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=10, choices=PURPOSES)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)


class AdminRecoveryCode(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_recovery_codes",
    )
    code_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=("user", "used_at"))]
