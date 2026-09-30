"""
GLORYBELLE — Seed Catalog Data.

Creates sample products matching the demo HTML (Infinity Mini, Cascade, etc.)
Includes a variant with ZERO stock (Oro Rosa) for "coming soon" testing.

Usage: python manage.py seed_catalog
"""
from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product, ProductVariant


class Command(BaseCommand):
    help = "Seed the catalog with sample products matching the demo."

    def handle(self, *args, **options):
        self.stdout.write("Seeding catalog...")

        # ── Categories ──
        anelli, _ = Category.objects.get_or_create(
            slug="anelli",
            defaults={"name": "Anelli", "sort_order": 1},
        )
        collane, _ = Category.objects.get_or_create(
            slug="collane",
            defaults={"name": "Collane", "sort_order": 2},
        )
        orecchini, _ = Category.objects.get_or_create(
            slug="orecchini",
            defaults={"name": "Orecchini", "sort_order": 3},
        )
        bracciali, _ = Category.objects.get_or_create(
            slug="bracciali",
            defaults={"name": "Bracciali", "sort_order": 4},
        )

        # ── Products ──
        products_data = [
            {
                "category": anelli,
                "name": "Infinity Mini",
                "slug": "infinity-mini",
                "description": (
                    "Un anello delicato che richiama il simbolo dell'infinito, "
                    "realizzato in oro 18 carati con finitura lucida."
                ),
                "base_price": "149.00",
                "metal": "gold",
                "gem": "none",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["48", "50", "52", "54"],
            },
            {
                "category": anelli,
                "name": "Eternity Band",
                "slug": "eternity-band",
                "description": (
                    "Fascia classica con diamanti incastonati lungo l'intera "
                    "circonferenza. Eleganza senza tempo."
                ),
                "base_price": "289.00",
                "metal": "gold",
                "gem": "diamond",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["48", "50", "52", "54"],
            },
            {
                "category": collane,
                "name": "Cascade Pendant",
                "slug": "cascade-pendant",
                "description": (
                    "Pendente a cascata con piccole gocce d'oro che catturano "
                    "la luce ad ogni movimento."
                ),
                "base_price": "219.00",
                "metal": "gold",
                "gem": "none",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["Unica"],
            },
            {
                "category": collane,
                "name": "Serpente Chain",
                "slug": "serpente-chain",
                "description": (
                    "Catena a maglia serpente in argento 925, flessibile e "
                    "moderna. Perfetta da sola o con pendenti."
                ),
                "base_price": "89.00",
                "metal": "silver",
                "gem": "none",
                "purity": "925",
                "is_featured": False,
                "sizes": ["Unica"],
            },
            {
                "category": orecchini,
                "name": "Luna Studs",
                "slug": "luna-studs",
                "description": (
                    "Orecchini a bottone ispirati alla luna crescente, "
                    "con dettaglio in zaffiro naturale."
                ),
                "base_price": "179.00",
                "metal": "gold",
                "gem": "sapphire",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["Unica"],
            },
            {
                "category": orecchini,
                "name": "Goccia Drop",
                "slug": "goccia-drop",
                "description": (
                    "Orecchini pendenti a goccia in oro rosa, leggeri "
                    "e luminosi. Ideali per occasioni speciali."
                ),
                "base_price": "199.00",
                "metal": "rose",
                "gem": "none",
                "purity": "18K",
                "is_featured": False,
                "sizes": ["Unica"],
            },
            {
                "category": bracciali,
                "name": "Filo d'Oro",
                "slug": "filo-doro",
                "description": (
                    "Bracciale a filo sottile in oro 18 carati, impreziosito "
                    "da un piccolo diamante solitario."
                ),
                "base_price": "169.00",
                "metal": "gold",
                "gem": "diamond",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["S", "M", "L"],
            },
            {
                "category": bracciali,
                "name": "Cerchio Rigido",
                "slug": "cerchio-rigido",
                "description": (
                    "Bracciale rigido dalla forma circolare pura, in argento "
                    "925 con chiusura magnetica."
                ),
                "base_price": "119.00",
                "metal": "silver",
                "gem": "none",
                "purity": "925",
                "is_featured": False,
                "sizes": ["S", "M", "L"],
            },
            {
                "category": anelli,
                "name": "Solitaire Classic",
                "slug": "solitaire-classic",
                "description": (
                    "Il solitario per eccellenza. Diamante naturale taglio "
                    "brillante su montatura in oro 18K."
                ),
                "base_price": "399.00",
                "metal": "gold",
                "gem": "diamond",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["48", "50", "52", "54", "56"],
            },
            {
                "category": anelli,
                "name": "Twist Ring",
                "slug": "twist-ring",
                "description": (
                    "Anello a fascia intrecciata in oro rosa 18K. "
                    "Design contemporaneo, comfort quotidiano."
                ),
                "base_price": "159.00",
                "metal": "rose",
                "gem": "none",
                "purity": "18K",
                "is_featured": False,
                "sizes": ["48", "50", "52", "54"],
            },
            {
                "category": collane,
                "name": "Riviera Tennis",
                "slug": "riviera-tennis",
                "description": (
                    "Collana tennis con smeraldi e diamanti alternati. "
                    "L'eleganza italiana allo stato puro."
                ),
                "base_price": "459.00",
                "metal": "gold",
                "gem": "emerald",
                "purity": "18K",
                "is_featured": True,
                "sizes": ["Unica"],
            },
            {
                "category": orecchini,
                "name": "Cerchio Huggie",
                "slug": "cerchio-huggie",
                "description": (
                    "Piccoli cerchi aderenti al lobo, in oro 18K. "
                    "Perfetti per il layering."
                ),
                "base_price": "129.00",
                "metal": "gold",
                "gem": "none",
                "purity": "18K",
                "is_featured": False,
                "sizes": ["Unica"],
            },
        ]

        metals_for_variants = ["gold", "silver", "rose"]

        for pdata in products_data:
            sizes = pdata.pop("sizes")
            product, created = Product.objects.get_or_create(
                slug=pdata["slug"],
                defaults=pdata,
            )

            if created:
                for metal in metals_for_variants:
                    for size in sizes:
                        sku = (
                            f"{pdata['slug'].upper()[:8]}-"
                            f"{metal[:3].upper()}-{size}"
                        )
                        # Zero stock for rose gold — "coming soon" test case
                        stock = 0 if metal == "rose" else 10

                        # Price override for silver (cheaper)
                        price_override = None
                        if metal == "silver":
                            base = float(pdata["base_price"])
                            price_override = f"{base * 0.65:.2f}"

                        ProductVariant.objects.get_or_create(
                            product=product,
                            metal=metal,
                            size=size,
                            defaults={
                                "sku": sku,
                                "stock_quantity": stock,
                                "price_override": price_override,
                            },
                        )
                self.stdout.write(
                    self.style.SUCCESS(f"  ✓ {product.name} ({len(sizes)} sizes × 3 metals)")
                )
            else:
                self.stdout.write(f"  – {product.name} (already exists)")

        total_products = Product.objects.count()
        total_variants = ProductVariant.objects.count()
        zero_stock = ProductVariant.objects.filter(stock_quantity=0).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! {total_products} products, {total_variants} variants "
                f"({zero_stock} with zero stock for 'coming soon' testing)."
            )
        )
