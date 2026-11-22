"""
GLORYBELLE — Account Models.

CustomerProfile (OneToOne to User) and Address.
Per rule.md: Address uses PROTECT on delete — order history must stay intact.
Per PRD §3.2: guest checkout supported (Order can exist without a user).
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class CustomerProfile(models.Model):
    """
    Extended user profile.

    Uses OneToOne link to Django's built-in User model (not a custom
    AUTH_USER_MODEL) to avoid migration complexity.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("Utente"),
    )
    phone = models.CharField(
        _("Telefono"),
        max_length=20,
        blank=True,
        help_text=_("Es. +39 02 1234567"),
    )
    date_of_birth = models.DateField(
        _("Data di nascita"),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)

    class Meta:
        verbose_name = _("Profilo cliente")
        verbose_name_plural = _("Profili clienti")

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"


class Address(models.Model):
    """
    Customer shipping/billing address.

    on_delete=PROTECT: per rule.md, never delete an Address
    referenced by an existing order.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("Utente"),
    )
    first_name = models.CharField(_("Nome"), max_length=100)
    last_name = models.CharField(_("Cognome"), max_length=100)
    line1 = models.CharField(_("Indirizzo riga 1"), max_length=255)
    line2 = models.CharField(_("Indirizzo riga 2"), max_length=255, blank=True)
    city = models.CharField(_("Città"), max_length=100)
    province = models.CharField(
        _("Provincia"),
        max_length=10,
        help_text=_("Sigla provincia (es. MI, RM, TO)"),
    )
    postal_code = models.CharField(_("CAP"), max_length=10)
    country = models.CharField(_("Paese"), max_length=2, default="IT")
    is_default = models.BooleanField(_("Indirizzo predefinito"), default=False)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)

    class Meta:
        verbose_name = _("Indirizzo")
        verbose_name_plural = _("Indirizzi")
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.city} ({self.province})"

    def save(self, *args, **kwargs):
        # If this address is set as default, unset any other defaults
        if self.is_default:
            Address.objects.filter(
                user=self.user, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
