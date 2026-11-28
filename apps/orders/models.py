"""
GLORYBELLE — Order Models (with first-purchase discount fields).

P1 fix #8: idempotency_key field added.
New feature: discount_percent + discount_amount fields for first-purchase
discount (10% off for newly registered customers).
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Order(models.Model):
    """
    A customer order.

    Supports both authenticated users and guest checkout.
    Address fields are snapshotted at order creation time.
    """

    STATUS_CHOICES = [
        ("pending", _("In attesa di pagamento")),
        ("paid", _("Pagato")),
        ("processing", _("In lavorazione")),
        ("shipped", _("Spedito")),
        ("delivered", _("Consegnato")),
        ("cancelled", _("Annullato")),
        ("refunded", _("Rimborsato")),
    ]

    order_number = models.CharField(
        _("Numero ordine"),
        max_length=30,
        unique=True,
        db_index=True,
    )
    idempotency_key = models.CharField(
        _("Chiave idempotenza"),
        max_length=64,
        unique=True,
        db_index=True,
        default=uuid.uuid4,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("Utente"),
    )
    email = models.EmailField(_("Email"))
    status = models.CharField(
        _("Stato"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # Snapshotted shipping address
    shipping_first_name = models.CharField(_("Nome spedizione"), max_length=100)
    shipping_last_name = models.CharField(_("Cognome spedizione"), max_length=100)
    shipping_line1 = models.CharField(_("Indirizzo spedizione 1"), max_length=255)
    shipping_line2 = models.CharField(
        _("Indirizzo spedizione 2"), max_length=255, blank=True
    )
    shipping_city = models.CharField(_("Città spedizione"), max_length=100)
    shipping_province = models.CharField(_("Provincia spedizione"), max_length=10)
    shipping_postal_code = models.CharField(_("CAP spedizione"), max_length=10)
    shipping_country = models.CharField(
        _("Paese spedizione"), max_length=2, default="IT"
    )

    # Snapshotted billing address
    billing_first_name = models.CharField(
        _("Nome fatturazione"), max_length=100, blank=True
    )
    billing_last_name = models.CharField(
        _("Cognome fatturazione"), max_length=100, blank=True
    )
    billing_line1 = models.CharField(
        _("Indirizzo fatturazione 1"), max_length=255, blank=True
    )
    billing_line2 = models.CharField(
        _("Indirizzo fatturazione 2"), max_length=255, blank=True
    )
    billing_city = models.CharField(
        _("Città fatturazione"), max_length=100, blank=True
    )
    billing_province = models.CharField(
        _("Provincia fatturazione"), max_length=10, blank=True
    )
    billing_postal_code = models.CharField(
        _("CAP fatturazione"), max_length=10, blank=True
    )
    billing_country = models.CharField(
        _("Paese fatturazione"), max_length=2, default="IT"
    )

    # Totals — always server-calculated (rule.md: never trust client price)
    subtotal = models.DecimalField(_("Subtotale"), max_digits=10, decimal_places=2)

    # First-purchase discount fields (10% for newly registered customers)
    discount_percent = models.DecimalField(
        _("Percentuale sconto"),
        max_digits=5,
        decimal_places=2,
        default="0.00",
        help_text=_("Percentuale di sconto applicata (es. 10.00 per 10%)."),
    )
    discount_amount = models.DecimalField(
        _("Importo sconto"),
        max_digits=10,
        decimal_places=2,
        default="0.00",
        help_text=_("Importo dello sconto in euro."),
    )
    discount_product_name = models.CharField(
        _("Prodotto scontato"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Il prodotto (una unità) a cui è stato applicato lo sconto di benvenuto."),
    )

    shipping_cost = models.DecimalField(
        _("Costo spedizione"), max_digits=10, decimal_places=2, default="0.00"
    )
    total = models.DecimalField(_("Totale"), max_digits=10, decimal_places=2)

    # Stripe link
    stripe_payment_intent_id = models.CharField(
        _("Stripe PaymentIntent ID"),
        max_length=255,
        blank=True,
        db_index=True,
    )
    tracking_number = models.CharField(
        _("Numero di tracciamento"),
        max_length=100,
        blank=True,
    )
    archived_at = models.DateTimeField(
        _("Archiviato il"),
        null=True,
        blank=True,
        db_index=True,
    )
    archive_reason = models.TextField(_("Motivo archiviazione"), blank=True)

    notes = models.TextField(_("Note del cliente"), blank=True)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Ordine")
        verbose_name_plural = _("Ordini")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"Ordine {self.order_number}"


class OrderItem(models.Model):
    """A line item in an order — snapshotted at purchase time."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Ordine"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name=_("Variante"),
    )

    # Snapshotted product data at time of purchase
    product_name = models.CharField(_("Nome prodotto"), max_length=200)
    variant_metal = models.CharField(_("Metallo"), max_length=20)
    variant_metal_display = models.CharField(_("Metallo (display)"), max_length=50)
    variant_size = models.CharField(_("Misura"), max_length=20)
    sku = models.CharField(_("SKU"), max_length=50)
    unit_price = models.DecimalField(
        _("Prezzo unitario"), max_digits=10, decimal_places=2
    )
    quantity = models.PositiveIntegerField(_("Quantità"), default=1)
    line_total = models.DecimalField(
        _("Totale riga"), max_digits=10, decimal_places=2
    )

    class Meta:
        verbose_name = _("Articolo ordine")
        verbose_name_plural = _("Articoli ordine")

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class OrderAdminNote(models.Model):
    """Private staff note; never included in customer-facing order serializers."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="admin_notes",
        verbose_name=_("Ordine"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_admin_notes",
        verbose_name=_("Autore"),
    )
    body = models.TextField(_("Nota interna"))
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)

    class Meta:
        verbose_name = _("Nota interna ordine")
        verbose_name_plural = _("Note interne ordine")
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Nota ordine {self.order.order_number} ({self.created_at:%Y-%m-%d})"
