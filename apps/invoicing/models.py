"""
GLORYBELLE — Invoice Models.

Italian electronic invoicing (Fatturazione Elettronica / SDI) via Fattura24.
Per architecture.md: invoice generation is a Celery task — a Fattura24
outage must not block checkout.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Invoice(models.Model):
    """
    Italian electronic invoice (Fattura Elettronica) linked to an Order.

    Generated asynchronously via Celery after payment is confirmed.
    Submitted to SDI through the Fattura24 API.
    """

    STATUS_CHOICES = [
        ("pending", _("In attesa")),
        ("submitted", _("Inviata")),
        ("accepted", _("Accettata")),
        ("rejected", _("Rifiutata")),
        ("error", _("Errore")),
    ]

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="invoice",
        verbose_name=_("Ordine"),
    )
    invoice_number = models.CharField(
        _("Numero fattura"),
        max_length=30,
        unique=True,
        db_index=True,
    )
    fattura24_id = models.CharField(
        _("Fattura24 ID"),
        max_length=255,
        blank=True,
        help_text=_("ID esterno assegnato da Fattura24."),
    )
    status = models.CharField(
        _("Stato"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    pdf_url = models.URLField(
        _("URL PDF"),
        blank=True,
        help_text=_("Link al PDF generato della fattura."),
    )
    xml_content = models.TextField(
        _("Contenuto XML"),
        blank=True,
        help_text=_("XML SDI-compliant (archiviato per audit)."),
    )
    error_message = models.TextField(
        _("Messaggio di errore"),
        blank=True,
    )
    attempts = models.PositiveIntegerField(
        _("Tentativi"),
        default=0,
        help_text=_("Numero di tentativi di invio."),
    )
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)

    class Meta:
        verbose_name = _("Fattura")
        verbose_name_plural = _("Fatture")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Fattura {self.invoice_number} — {self.get_status_display()}"
