from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class HeroImage(models.Model):
    media_asset = models.ForeignKey(
        "catalog.MediaAsset",
        on_delete=models.PROTECT,
        related_name="hero_images",
        verbose_name=_("Immagine"),
    )
    sort_order = models.PositiveIntegerField(_("Ordine"), default=0, db_index=True)
    active = models.BooleanField(_("Attiva"), default=True)
    created_at = models.DateTimeField(_("Creata il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornata il"), auto_now=True)

    class Meta:
        ordering = ["sort_order", "pk"]
        verbose_name = _("Immagine hero")
        verbose_name_plural = _("Immagini hero")

    def __str__(self):
        return f"Hero {self.pk} — {self.media_asset.alt_text or self.media_asset_id}"


class InstagramGrid(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    link = models.URLField(
        _("Link Instagram"),
        max_length=500,
        default="https://www.instagram.com/",
    )
    updated_at = models.DateTimeField(_("Aggiornata il"), auto_now=True)

    class Meta:
        verbose_name = _("Configurazione griglia Instagram")
        verbose_name_plural = _("Configurazione griglia Instagram")
        constraints = [
            models.CheckConstraint(
                condition=Q(pk=1),
                name="sitecontent_instagram_singleton",
            ),
        ]

    def __str__(self):
        return "Griglia Instagram"


class InstagramGridImage(models.Model):
    grid = models.ForeignKey(
        InstagramGrid,
        on_delete=models.CASCADE,
        related_name="images",
    )
    media_asset = models.ForeignKey(
        "catalog.MediaAsset",
        on_delete=models.PROTECT,
        related_name="instagram_images",
        verbose_name=_("Immagine"),
    )
    position = models.PositiveSmallIntegerField(_("Posizione"))

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("Immagine Instagram")
        verbose_name_plural = _("Immagini Instagram")
        constraints = [
            models.UniqueConstraint(
                fields=["grid", "position"],
                name="sitecontent_instagram_position_unique",
            ),
            models.UniqueConstraint(
                fields=["grid", "media_asset"],
                name="sitecontent_instagram_asset_unique",
            ),
            models.CheckConstraint(
                condition=Q(position__lte=6),
                name="sitecontent_instagram_position_lte_6",
            ),
        ]

    def __str__(self):
        return f"Instagram {self.position + 1}"


class Testimonial(models.Model):
    name = models.CharField(_("Nome"), max_length=120)
    quote = models.TextField(_("Recensione"), max_length=2000)
    photo_asset = models.ForeignKey(
        "catalog.MediaAsset",
        on_delete=models.PROTECT,
        related_name="testimonial_photos",
        verbose_name=_("Foto"),
    )
    active = models.BooleanField(_("Attiva"), default=True)
    created_at = models.DateTimeField(_("Creata il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornata il"), auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Testimonianza")
        verbose_name_plural = _("Testimonianze")

    def __str__(self):
        return self.name
