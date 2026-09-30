"""
GLORYBELLE — Invoice Models.

Italian electronic invoicing (Fatturazione Elettronica / SDI) via Fattura24.
Per architecture.md: invoice generation is a Celery task — a Fattura24
outage must not block checkout.
"""
from django.db import models


class Invoice(models.Model):
    """
    Italian electronic invoice (Fattura Elettronica) linked to an Order.

    Generated asynchronously via Celery after payment is confirmed.
    Submitted to SDI through the Fattura24 API.
    """

    STATUS_CHOICES = [
        ("pending", "In attesa"),
        ("submitted", "Inviata"),
        ("accepted", "Accettata"),
        ("rejected", "Rifiutata"),
        ("error", "Errore"),
    ]

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="invoice",
        verbose_name="Ordine",
    )
    invoice_number = models.CharField(
        "Numero fattura",
        max_length=30,
        unique=True,
        db_index=True,
    )
    fattura24_id = models.CharField(
        "Fattura24 ID",
        max_length=255,
        blank=True,
        help_text="ID esterno assegnato da Fattura24.",
    )
    status = models.CharField(
        "Stato",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    pdf_url = models.URLField(
        "URL PDF",
        blank=True,
        help_text="Link al PDF generato della fattura.",
    )
    xml_content = models.TextField(
        "Contenuto XML",
        blank=True,
        help_text="XML SDI-compliant (archiviato per audit).",
    )
    error_message = models.TextField(
        "Messaggio di errore",
        blank=True,
    )
    attempts = models.PositiveIntegerField(
        "Tentativi",
        default=0,
        help_text="Numero di tentativi di invio.",
    )
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Fattura"
        verbose_name_plural = "Fatture"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Fattura {self.invoice_number} — {self.get_status_display()}"
