"""
GLORYBELLE — Catalog Models.

Category, Product, ProductVariant, ProductImage.
Per architecture.md: each variant has independent stock (metal × size).
Per rule.md: never delete a ProductVariant referenced by an existing order (PROTECT).
"""
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """Product category (e.g., Anelli, Collane, Orecchini)."""

    name = models.CharField("Nome", max_length=100)
    slug = models.SlugField("Slug", max_length=120, unique=True, db_index=True)
    description = models.TextField("Descrizione", blank=True)
    image = models.ImageField(
        "Immagine",
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
        verbose_name="Categoria padre",
    )
    is_active = models.BooleanField("Attiva", default=True, db_index=True)
    sort_order = models.PositiveIntegerField("Ordine", default=0)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Categoria"
        verbose_name_plural = "Categorie"
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
        ("gold", "Oro 18K"),
        ("rose", "Oro Rosa"),
        ("silver", "Argento 925"),
    ]

    GEM_CHOICES = [
        ("diamond", "Diamante"),
        ("emerald", "Smeraldo"),
        ("ruby", "Rubino"),
        ("sapphire", "Zaffiro"),
        ("amethyst", "Ametista"),
        ("none", "Nessuna"),
    ]

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Categoria",
    )
    name = models.CharField("Nome", max_length=200)
    slug = models.SlugField("Slug", max_length=220, unique=True, db_index=True)
    description = models.TextField("Descrizione", blank=True)
    base_price = models.DecimalField(
        "Prezzo base",
        max_digits=10,
        decimal_places=2,
        help_text="Prezzo di listino in EUR. Le varianti possono sovrascriverlo.",
    )
    metal = models.CharField(
        "Metallo predefinito",
        max_length=20,
        choices=METAL_CHOICES,
        default="gold",
    )
    gem = models.CharField(
        "Pietra",
        max_length=20,
        choices=GEM_CHOICES,
        default="none",
        blank=True,
    )
    purity = models.CharField(
        "Purezza",
        max_length=20,
        default="18K",
        help_text="Es. 18K, 925, etc.",
    )
    is_active = models.BooleanField("Attivo", default=True, db_index=True)
    is_featured = models.BooleanField("In evidenza", default=False, db_index=True)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Prodotto"
        verbose_name_plural = "Prodotti"
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
        return self.images.filter(is_primary=True).first() or self.images.first()


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
        verbose_name="Prodotto",
    )
    metal = models.CharField("Metallo", max_length=20, choices=METAL_CHOICES)
    size = models.CharField(
        "Misura",
        max_length=20,
        help_text="Es. 50, 52, 54 per anelli; Unica per collane.",
    )
    sku = models.CharField(
        "SKU",
        max_length=50,
        unique=True,
        db_index=True,
    )
    price_override = models.DecimalField(
        "Prezzo personalizzato",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Se impostato, sovrascrive il prezzo base del prodotto.",
    )
    stock_quantity = models.PositiveIntegerField("Quantità in stock", default=0)
    reserved_quantity = models.PositiveIntegerField(
        "Quantità riservata",
        default=0,
        help_text="Stock riservato da carrelli attivi (gestito da cart/services.py).",
    )
    is_active = models.BooleanField("Attiva", default=True, db_index=True)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)
    updated_at = models.DateTimeField("Aggiornato il", auto_now=True)

    class Meta:
        verbose_name = "Variante"
        verbose_name_plural = "Varianti"
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
        verbose_name="Prodotto",
    )
    image = models.ImageField(
        "Immagine principale",
        upload_to="products/",
        help_text="Foto principale (1:1, soggetto centrato).",
    )
    image_alt = models.ImageField(
        "Immagine alternativa (hover)",
        upload_to="products/",
        blank=True,
        null=True,
        help_text="Seconda foto per hover-swap (stesso formato 1:1).",
    )
    alt_text = models.CharField(
        "Testo alternativo",
        max_length=200,
        blank=True,
        help_text="Descrizione per accessibilità.",
    )
    is_primary = models.BooleanField("Immagine principale", default=False)
    sort_order = models.PositiveIntegerField("Ordine", default=0)
    created_at = models.DateTimeField("Creato il", auto_now_add=True)

    class Meta:
        verbose_name = "Immagine prodotto"
        verbose_name_plural = "Immagini prodotto"
        ordering = ["sort_order"]

    def __str__(self):
        return f"Immagine {self.sort_order} — {self.product.name}"
