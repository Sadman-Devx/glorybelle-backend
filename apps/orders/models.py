"""
GLORYBELLE — Order Models.

Order and OrderItem with snapshotted line-item data.
Per roadmap Day 6: "snapshots line items (price/name at time of purchase,
so later catalog edits never retroactively change a past order)."
Per PRD §3.2: guest checkout supported (Order can exist without a user).
Per rule.md: never delete a ProductVariant referenced by an existing order (PROTECT).
"""
from django.conf import settings
from django.db import models


class Order(models.Model):
    """
    A customer order.

    Supports both authenticated users and guest checkout.
    Address fields are snapshotted at order creation time — not FK references —
    so editing an address after purchase never changes a past order.
    """

    STATUS_CHOICES = [
        ("pending", "In attesa di pagamento"),
        ("paid", "Pagato"),
        ("processing", "In lavorazione"),
        ("shipped", "Spedito"),
        ("delivered", "Consegnato"),
        ("cancelled", "Annullato"),
        ("refunded", "Rimborsato"),
    ]

    order_number = models.CharField(
        "Numero ordine",
        max_length=30,
        unique=True,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name="Utente",
        help_text="Null per ordini guest (PRD §3.2 Gift Buyer).",
    )
    email = models.EmailField(
        "Email",
        help_text="Email del cliente — richiesta anche per ordini guest.",
    )
    status = models.CharField(
        "Stato",
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        db_index=True,
    )

    # Snapshotted shipping address
    shipping_first_name = models.CharField("Nome spedizione", max_length=100)
    shipping_last_name = models.CharField("Cognome spedizione", max_length=100)
    shipping_line1 = models.CharField("Indirizzo spedizione 1", max_length=255)
    shipping_line2 = models.CharField(
        "Indirizzo spedizione 2", max_length=255, blank=True
    )
    shipping_city = models.CharField("Città spedizione", max_length=100)
    shipping_province = models.CharField("Provincia spedizione", max_length=10)
    shipping_postal_code = models.CharField("CAP spedizione", max_length=10)
    shipping_country = models.CharField(
        "Paese spedizione", max_length=2, default="IT"
    )

    # Snapshotted billing address
    billing_first_name = models.CharField(
        "Nome fatturazione", max_length=100, blank=True
    )
    billing_last_name = models.CharField(
        "Cognome fatturazione", max_length=100, blank=True
    )
    billing_line1 = models.CharField(
        "Indirizzo fatturazione 1", max_length=255, blank=True
    )
    billing_line2 = models.CharField(
        "Indirizzo fatturazione 2", max_length=255, blank=True
    )
    billing_city = models.CharField(
        "Città fatturazione", max_length=100, blank=True
    )
    billing_province = models.CharField(
        "Provincia fatturazione", max_length=10, blank=True
    )
    billing_postal_code = models.CharField(
        "CAP fatturazione", max_length=10, blank=True
    )
    billing_country = models.CharField(
        "Paese fatturazione", max_length=2, default="IT"
    )

    # Totals — always server-calculated (rule.md: never trust client price)
    subtotal = models.DecimalField(
        "Subtotale", max_digits=10, decimal_places=2
    )
    shipping_cost = models.DecimalField(
        "Costo spedizione", max_digits=10, decimal_places=2, default="0.00"
    )
    total = models.DecimalField("Totale", max_digits=10, decimal_places=2)

    # Stripe link
    stripe_payment_intent_id = models.CharField(
        "Stripe PaymentIntent ID",
        max_length=255,
        blank=True,
        db_index=True,
    )

    notes = models.TextField("Note del cliente", blank=True)

    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Ordine"
        verbose_name_plural = "Ordini"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"Ordine {self.order_number}"


class OrderItem(models.Model):
    """
    A line item in an order — snapshotted at purchase time.

    All display fields (product_name, variant_metal, variant_size, sku,
    unit_price) are copied from the catalog at order creation. This means
    later edits to a product's name, price, or SKU never change a past order.

    variant FK uses PROTECT — per rule.md: never delete a ProductVariant
    referenced by an existing order.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Ordine",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Variante",
    )

    # Snapshotted product data at time of purchase
    product_name = models.CharField("Nome prodotto", max_length=200)
    variant_metal = models.CharField("Metallo", max_length=20)
    variant_metal_display = models.CharField(
        "Metallo (display)", max_length=50
    )
    variant_size = models.CharField("Misura", max_length=20)
    sku = models.CharField("SKU", max_length=50)
    unit_price = models.DecimalField(
        "Prezzo unitario", max_digits=10, decimal_places=2
    )
    quantity = models.PositiveIntegerField("Quantità", default=1)
    line_total = models.DecimalField(
        "Totale riga", max_digits=10, decimal_places=2
    )

    class Meta:
        verbose_name = "Articolo ordine"
        verbose_name_plural = "Articoli ordine"

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"
