"""
GLORYBELLE — Catalog Models.

Category, Product, ProductVariant, ProductImage.
Per architecture.md: each variant has independent stock (metal × size).
Per rule.md: never delete a ProductVariant referenced by an existing order (PROTECT).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class Category(models.Model):
    """Product category (e.g., Anelli, Collane, Orecchini)."""

    name = models.CharField(_("Nome"), max_length=100)
    slug = models.SlugField(_("Slug"), max_length=120, unique=True, db_index=True)
    description = models.TextField(_("Descrizione"), blank=True)
    image = models.ImageField(
        _("Immagine"),
        upload_to="categories/",
        blank=True,
        null=True,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Categoria padre"),
    )
    is_active = models.BooleanField(_("Attiva"), default=True, db_index=True)
    sort_order = models.PositiveIntegerField(_("Ordine"), default=0)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)

    class Meta:
        verbose_name = _("Categoria")
        verbose_name_plural = _("Categorie")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(models.Model):
    """
    A product in the catalog.

    Price strategy: base_price is the default. Each ProductVariant can
    override with price_override. The frontend/API always resolves
    the final price server-side (rule.md: never trust client price).
    """

    METAL_CHOICES = [
        ("gold", _("Oro 18K")),
        ("rose", _("Oro Rosa")),
        ("silver", _("Argento 925")),
    ]

    GEM_CHOICES = [
        ("diamond", _("Diamante")),
        ("emerald", _("Smeraldo")),
        ("ruby", _("Rubino")),
        ("sapphire", _("Zaffiro")),
        ("amethyst", _("Ametista")),
        ("none", _("Nessuna")),
    ]

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("Categoria"),
    )
    name = models.CharField(_("Nome"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=220, unique=True, db_index=True)
    description = models.TextField(_("Descrizione"), blank=True)
    base_price = models.DecimalField(
        _("Prezzo base"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Prezzo di listino in EUR. Le varianti possono sovrascriverlo."),
    )
    metal = models.CharField(
        _("Metallo predefinito"),
        max_length=20,
        choices=METAL_CHOICES,
        default="gold",
    )
    gem = models.CharField(
        _("Pietra"),
        max_length=20,
        choices=GEM_CHOICES,
        default="none",
        blank=True,
    )
    purity = models.CharField(
        _("Purezza"),
        max_length=20,
        default="18K",
        help_text=_("Es. 18K, 925, etc."),
    )
    is_active = models.BooleanField(_("Attivo"), default=True, db_index=True)
    is_featured = models.BooleanField(_("In evidenza"), default=False, db_index=True)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Prodotto")
        verbose_name_plural = _("Prodotti")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["metal", "is_active"]),
            models.Index(fields=["is_featured", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def primary_image(self):
        """Return the primary ProductImage, or the first one."""
        images = list(self.images.all())
        return next((image for image in images if image.is_primary), None) or (
            images[0] if images else None
        )


class ProductVariant(models.Model):
    """
    A specific variant of a product (metal × size combination).

    Each variant has independent stock. This is the entity that gets
    added to a cart and purchased.

    CRITICAL (rule.md): Never touch stock_quantity or reserved_quantity
    outside select_for_update() inside transaction.atomic().
    """

    METAL_CHOICES = Product.METAL_CHOICES

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("Prodotto"),
    )
    metal = models.CharField(_("Metallo"), max_length=20, choices=METAL_CHOICES)
    size = models.CharField(
        _("Misura"),
        max_length=20,
        help_text=_("Es. 50, 52, 54 per anelli; Unica per collane."),
    )
    sku = models.CharField(
        _("SKU"),
        max_length=50,
        unique=True,
        db_index=True,
    )
    price_override = models.DecimalField(
        _("Prezzo personalizzato"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Se impostato, sovrascrive il prezzo base del prodotto."),
    )
    stock_quantity = models.PositiveIntegerField(_("Quantità in stock"), default=0)
    reserved_quantity = models.PositiveIntegerField(
        _("Quantità riservata"),
        default=0,
        help_text=_("Stock riservato da carrelli attivi (gestito da cart/services.py)."),
    )
    is_active = models.BooleanField(_("Attiva"), default=True, db_index=True)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Aggiornato il"), auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Variante")
        verbose_name_plural = _("Varianti")
        unique_together = [("product", "metal", "size")]
        ordering = ["metal", "size"]
        indexes = [
            models.Index(fields=["product", "is_active"]),
        ]

    def __str__(self):
        return f"{self.product.name} — {self.get_metal_display()} · {self.size}"

    @property
    def price(self):
        """Resolved price: variant override or product base price."""
        if self.price_override is not None:
            return self.price_override
        return self.product.base_price

    @property
    def available_stock(self):
        """Real availability: stock minus what's reserved by active carts."""
        return max(0, self.stock_quantity - self.reserved_quantity)


class ProductImage(models.Model):
    """
    Product images.

    Per design.md §4.6.1: each product card supports two images —
    primary (img) and alternate (img2) for hover-swap. Both are
    uploaded through admin, delivered via Cloudinary.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Prodotto"),
    )
    media_asset = models.ForeignKey(
        "MediaAsset",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="product_images",
        verbose_name=_("Risorsa multimediale"),
    )
    image = models.ImageField(
        _("Immagine principale"),
        upload_to="products/",
        blank=True,
        help_text=_("Foto principale (1:1, soggetto centrato)."),
    )
    image_alt = models.ImageField(
        _("Immagine alternativa (hover)"),
        upload_to="products/",
        blank=True,
        null=True,
        help_text=_("Seconda foto per hover-swap (stesso formato 1:1)."),
    )
    alt_text = models.CharField(
        _("Testo alternativo"),
        max_length=200,
        blank=True,
        help_text=_("Descrizione per accessibilità."),
    )
    is_primary = models.BooleanField(_("Immagine principale"), default=False)
    sort_order = models.PositiveIntegerField(_("Ordine"), default=0)
    created_at = models.DateTimeField(_("Creato il"), auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _("Immagine prodotto")
        verbose_name_plural = _("Immagini prodotto")
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_one_primary_image_per_product",
            ),
            models.UniqueConstraint(
                fields=["product", "media_asset"],
                condition=Q(media_asset__isnull=False),
                name="catalog_unique_product_media_asset",
            ),
        ]

    def __str__(self):
        return f"Immagine {self.sort_order} — {self.product.name}"


class MediaAsset(models.Model):
    """Sanitized, responsive WebP rendition set stored in the admin media bucket."""

    object_key_400 = models.CharField(max_length=512, unique=True)
    object_key_800 = models.CharField(max_length=512, unique=True)
    object_key_1600 = models.CharField(max_length=512, unique=True)
    original_size_bytes = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    alt_text = models.CharField(max_length=200, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_catalog_media",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Media {self.pk}"


class PendingMediaUpload(models.Model):
    """A short-lived, manager-owned object key awaiting server-side validation."""

    object_key = models.CharField(max_length=512, unique=True)
    content_type = models.CharField(max_length=32)
    declared_size_bytes = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pending_catalog_media_uploads",
    )
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
