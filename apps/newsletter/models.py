"""
GLORYBELLE — Newsletter Models.

Per PRD §3.2: Newsletter signup (footer).
"""
import uuid

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
    is_confirmed = models.BooleanField(
        _("Confermato"),
        default=False,
        help_text=_("Attivato solo dopo il click sul link di conferma."),
    )
    confirmation_nonce = models.UUIDField(
        _("Nonce conferma"),
        default=uuid.uuid4,
        editable=False,
    )
    confirmation_sent_at = models.DateTimeField(
        _("Ultima email di conferma"),
        null=True,
        blank=True,
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
        if not self.is_active:
            status = "disiscritto"
        elif not self.is_confirmed:
            status = "in attesa di conferma"
        else:
            status = "attivo"
        return f"{self.email} ({status})"
