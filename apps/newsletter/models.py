"""
GLORYBELLE — Newsletter Models.

Per PRD §3.2: Newsletter signup (footer).
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class NewsletterSubscriber(models.Model):
    """
    Newsletter subscriber.

    Public signup — no account required.
    Soft-delete via is_active flag for GDPR compliance.
    """

    email = models.EmailField(
        _("Email"),
        unique=True,
        db_index=True,
    )
    is_active = models.BooleanField(
        _("Attivo"),
        default=True,
        help_text=_("Disattivato quando l'utente annulla l'iscrizione."),
    )
    subscribed_at = models.DateTimeField(
        _("Iscritto il"),
        auto_now_add=True,
    )
    unsubscribed_at = models.DateTimeField(
        _("Disiscritto il"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Iscritto newsletter")
        verbose_name_plural = _("Iscritti newsletter")
        ordering = ["-subscribed_at"]

    def __str__(self):
        status = "attivo" if self.is_active else "disiscritto"
        return f"{self.email} ({status})"
