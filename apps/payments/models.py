"""
GLORYBELLE — Payment Models.

Payment and ProcessedWebhookEvent for idempotent Stripe webhook handling.
Per rule.md: "Never process a Stripe webhook without checking
ProcessedWebhookEvent first."
"""
from django.db import models


class Payment(models.Model):
    """
    Payment record linked to an Order.

    Tracks Stripe PaymentIntent lifecycle. Source of truth for
    "was this order actually paid" is the Stripe webhook, not
    the client redirect (architecture.md §1.3).
    """

    STATUS_CHOICES = [
        ("pending", "In attesa"),
        ("succeeded", "Riuscito"),
        ("failed", "Fallito"),
        ("refunded", "Rimborsato"),
    ]

    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="payment",
        verbose_name="Ordine",
    )
    stripe_payment_intent_id = models.CharField(
        "Stripe PaymentIntent ID",
        max_length=255,
        unique=True,
        db_index=True,
    )
    stripe_charge_id = models.CharField(
        "Stripe Charge ID",
        max_length=255,
        blank=True,
    )
    amount = models.DecimalField(
        "Importo",
        max_digits=10,
        decimal_places=2,
    )
    currency = models.CharField(
        "Valuta",
        max_length=3,
        default="EUR",
    )
    status = models.CharField(
        "Stato",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )
    idempotency_key = models.CharField(
        "Chiave idempotenza",
        max_length=255,
        unique=True,
        help_text="Chiave usata per creare il PaymentIntent su Stripe.",
    )
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamenti"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Pagamento {self.stripe_payment_intent_id} — {self.get_status_display()}"


class ProcessedWebhookEvent(models.Model):
    """
    Record of a processed Stripe webhook event.

    This is the idempotency guard: before processing any webhook,
    check if the event ID already exists here. If it does, skip
    processing (return 200 to Stripe so it stops retrying).

    Per rule.md: "Never process a Stripe webhook without checking
    ProcessedWebhookEvent first. Stripe redelivers events;
    unguarded webhook logic double-processes orders."
    """

    stripe_event_id = models.CharField(
        "Stripe Event ID",
        max_length=255,
        unique=True,
        db_index=True,
    )
    event_type = models.CharField(
        "Tipo evento",
        max_length=100,
        help_text="Es. payment_intent.succeeded",
    )
    processed_at = models.DateTimeField("Elaborato il", auto_now_add=True)

    class Meta:
        verbose_name = "Evento webhook elaborato"
        verbose_name_plural = "Eventi webhook elaborati"
        ordering = ["-processed_at"]

    def __str__(self):
        return f"{self.event_type} — {self.stripe_event_id}"
