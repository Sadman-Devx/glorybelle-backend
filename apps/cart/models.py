"""
GLORYBELLE — Cart Models.

Cart, CartItem, StockReservation.
Per architecture.md §1.3: stock reservation with 15-minute expiry.
Per PRD §3.3: persistent cart (guest session + logged-in, merged on login).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.catalog.models import ProductVariant


class Cart(models.Model):
    """
    Shopping cart.

    Supports both authenticated users and guest sessions.
    Guest carts use session_key; logged-in carts use user FK.
    Merged on login (see services.py).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="carts",
        verbose_name="Utente",
    )
    session_key = models.CharField(
        "Chiave sessione",
        max_length=40,
        null=True,
        blank=True,
        db_index=True,
        help_text="Per carrelli di utenti non registrati.",
    )
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Carrello"
        verbose_name_plural = "Carrelli"

    def __str__(self):
        if self.user:
            return f"Carrello di {self.user.username}"
        return f"Carrello guest ({self.session_key})"

    @property
    def total(self):
        """Calculate cart total from items."""
        return sum(item.line_total for item in self.items.all())

    @property
    def item_count(self):
        """Total quantity of all items."""
        return sum(item.quantity for item in self.items.all())


class CartItem(models.Model):
    """
    A line item in the cart.

    Links to a specific ProductVariant (metal × size combination).
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Carrello",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="cart_items",
        verbose_name="Variante",
    )
    quantity = models.PositiveIntegerField("Quantità", default=1)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Articolo nel carrello"
        verbose_name_plural = "Articoli nel carrello"
        unique_together = [("cart", "variant")]

    def __str__(self):
        return f"{self.variant} × {self.quantity}"

    @property
    def line_total(self):
        """Price × quantity for this line item."""
        return self.variant.price * self.quantity


class StockReservation(models.Model):
    """
    Temporary stock reservation tied to a cart item.

    Per architecture.md: 15-minute expiry. Prevents overselling by
    holding stock while the customer is in the checkout flow.

    Cleaned up by Celery beat task (cart/tasks.py) every 60 seconds.
    """

    cart_item = models.ForeignKey(
        CartItem,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="Articolo carrello",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="reservations",
        verbose_name="Variante",
    )
    quantity = models.PositiveIntegerField("Quantità riservata")
    expires_at = models.DateTimeField("Scade il", db_index=True)
    is_active = models.BooleanField("Attiva", default=True, db_index=True)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)

    class Meta:
        verbose_name = "Riserva stock"
        verbose_name_plural = "Riserve stock"
        indexes = [
            models.Index(fields=["is_active", "expires_at"]),
        ]

    def __str__(self):
        status = "attiva" if self.is_active else "scaduta"
        return f"Riserva {self.quantity}× {self.variant} ({status})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at
