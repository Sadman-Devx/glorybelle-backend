"""
GLORYBELLE — Review Models.

Per PRD §3.4: Customer reviews, moderated before publish.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """
    Customer review for a product.

    Per PRD §3.4: reviews are moderated — is_approved must be set to True
    by an admin before the review is visible in the public API.
    One review per user per product (unique_together).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Utente",
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Prodotto",
    )
    rating = models.PositiveSmallIntegerField(
        "Valutazione",
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Da 1 a 5 stelle.",
    )
    title = models.CharField(
        "Titolo",
        max_length=200,
    )
    body = models.TextField(
        "Testo",
    )
    is_approved = models.BooleanField(
        "Approvata",
        default=False,
        db_index=True,
        help_text="Le recensioni devono essere approvate prima di essere pubblicate.",
    )
    created_at = models.DateTimeField("Creata il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornata il", auto_now=True)

    class Meta:
        verbose_name = "Recensione"
        verbose_name_plural = "Recensioni"
        unique_together = [("user", "product")]
        ordering = ["-created_at"]

    def __str__(self):
        stars = "★" * self.rating + "☆" * (5 - self.rating)
        return f"{stars} {self.title} — {self.user.username}"
