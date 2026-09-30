"""
GLORYBELLE — Wishlist Models.

Per PRD §3.2: Wishlist (heart toggle, persisted per account).
Simple toggle — no quantity, no variants.
"""
from django.conf import settings
from django.db import models


class WishlistItem(models.Model):
    """
    A product in the user's wishlist.

    One entry per user × product pair. Toggle behavior is handled
    in views.py (add if absent, remove if present).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name="Utente",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
        verbose_name="Prodotto",
    )
    created_at = models.DateTimeField("Aggiunto il", auto_now_add=True)

    class Meta:
        verbose_name = "Articolo lista desideri"
        verbose_name_plural = "Articoli lista desideri"
        unique_together = [("user", "product")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} ♥ {self.product.name}"
