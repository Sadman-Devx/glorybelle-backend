"""
GLORYBELLE — Newsletter Models.

Per PRD §3.2: Newsletter signup (footer).
"""
from django.db import models


class NewsletterSubscriber(models.Model):
    """
    Newsletter subscriber.

    Public signup — no account required.
    Soft-delete via is_active flag for GDPR compliance.
    """

    email = models.EmailField(
        "Email",
        unique=True,
        db_index=True,
    )
    is_active = models.BooleanField(
        "Attivo",
        default=True,
        help_text="Disattivato quando l'utente annulla l'iscrizione.",
    )
    subscribed_at = models.DateTimeField(
        "Iscritto il",
        auto_now_add=True,
    )
    unsubscribed_at = models.DateTimeField(
        "Disiscritto il",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Iscritto newsletter"
        verbose_name_plural = "Iscritti newsletter"
        ordering = ["-subscribed_at"]

    def __str__(self):
        status = "attivo" if self.is_active else "disiscritto"
        return f"{self.email} ({status})"
