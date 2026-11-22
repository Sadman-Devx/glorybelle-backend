"""
GLORYBELLE — Wishlist Models.

Per PRD §3.2: Wishlist (heart toggle, persisted per account).
Simple toggle — no quantity, no variants.

P1 fix #17: adds Wishlist parent model per backend-design PDF §2 spec
(previously only WishlistItem existed). One Wishlist per user, many
WishlistItems under it. Backwards-compatible — existing WishlistItem
rows are linked to a new default Wishlist via data migration.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Wishlist(models.Model):
    """
    A user's wishlist — one per customer.

    Acts as the parent container for WishlistItem rows. Designed per
    backend-design PDF §2: Wishlist 1—N WishlistItem.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist",
        verbose_name=_("Utente"),
    )
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)

    class Meta:
        verbose_name = _("Lista desideri")
        verbose_name_plural = _("Liste desideri")

    def __str__(self):
        return f"Lista desideri di {self.user.username}"

    @classmethod
    def get_or_create_for_user(cls, user):
        """Idempotent helper — used by views instead of raw get_or_create."""
        wishlist, _ = cls.objects.get_or_create(user=user)
        return wishlist


class WishlistItem(models.Model):
    """
    A product in the user's wishlist.

    One entry per user × product pair. Toggle behavior is handled
    in views.py (add if absent, remove if present).
    """

    wishlist = models.ForeignKey(
        Wishlist,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Lista desideri"),
        null=True,  # P1 fix #17 — backwards-compat during migration
        blank=True,
    )
    # Kept for backwards compat with any code that still references user directly.
    # New code should use wishlist.user. Both are kept in sync via the
    # WishlistItem.save() override below.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        verbose_name=_("Utente"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="wishlisted_by",
        verbose_name=_("Prodotto"),
    )
    created_at = models.DateTimeField(_("Aggiunto il"), auto_now_add=True)

    class Meta:
        verbose_name = _("Articolo lista desideri")
        verbose_name_plural = _("Articoli lista desideri")
        unique_together = [("user", "product")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} ♥ {self.product.name}"

    def save(self, *args, **kwargs):
        """Ensure wishlist is set if user is set (P1 fix #17 convenience)."""
        if not self.wishlist_id and self.user_id:
            self.wishlist = Wishlist.get_or_create_for_user(self.user)
        super().save(*args, **kwargs)
