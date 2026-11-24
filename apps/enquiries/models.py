from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Enquiry(models.Model):
    TOPIC_CHOICES = [
        ("prodotto", _("Informazioni su un prodotto")),
        ("ordine", _("Informazioni su un ordine")),
        ("atelier", _("Atelier")),
        ("altro", _("Altro")),
    ]
    ATELIER_TYPE_CHOICES = [
        ("anelli", _("Anelli")),
        ("collane", _("Collane")),
        ("orecchini", _("Orecchini")),
    ]
    STATUS_CHOICES = [
        ("new", _("Nuova")),
        ("in_progress", _("In lavorazione")),
        ("answered", _("Risposta inviata")),
        ("closed", _("Chiusa")),
    ]

    name = models.CharField(_("Nome"), max_length=150)
    email = models.EmailField(_("Email"))
    topic = models.CharField(_("Argomento"), max_length=20, choices=TOPIC_CHOICES)
    message = models.TextField(_("Messaggio"), max_length=5000)
    atelier_type = models.CharField(
        _("Tipo di Atelier"),
        max_length=20,
        choices=ATELIER_TYPE_CHOICES,
        blank=True,
    )
    status = models.CharField(
        _("Stato"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="new",
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_enquiries",
        verbose_name=_("Assegnata a"),
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(_("Creata il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornata il"), auto_now=True)

    class Meta:
        verbose_name = _("Richiesta")
        verbose_name_plural = _("Richieste")
        ordering = ["-created_at", "-pk"]
        indexes = [
            models.Index(fields=["topic", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_topic_display()} — {self.name}"


class EnquiryNote(models.Model):
    enquiry = models.ForeignKey(
        Enquiry,
        on_delete=models.CASCADE,
        related_name="internal_notes",
        verbose_name=_("Richiesta"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="enquiry_notes",
        verbose_name=_("Autore"),
        null=True,
        blank=True,
    )
    body = models.TextField(_("Nota interna"), max_length=5000)
    created_at = models.DateTimeField(_("Creata il"), auto_now_add=True)

    class Meta:
        verbose_name = _("Nota interna")
        verbose_name_plural = _("Note interne")
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Nota per richiesta #{self.enquiry_id}"
