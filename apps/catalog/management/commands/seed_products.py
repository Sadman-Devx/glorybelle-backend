"""
GLORYBELLE — Seed Products Management Command.

Creates sample categories, products, and variants for development/testing.
Images are NOT included — add real images through Django admin.

Usage:
    python manage.py seed_products          # Create seed data
    python manage.py seed_products --flush  # Delete all seed data first

NOTE: This is for development only. Do NOT run in production.
      Delete seed data before adding real products via admin.
"""
from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product, ProductImage, ProductVariant


SEED_DATA = {
    "categories": [
        {
            "name": "Anelli",
            "slug": "anelli",
            "description": "Anelli in oro e argento, con diamanti e pietre preziose.",
            "sort_order": 1,
        },
        {
            "name": "Collane",
            "slug": "collane",
            "description": "Collane artigianali italiane, dal delicato al vistoso.",
            "sort_order": 2,
        },
        {
            "name": "Orecchini",
            "slug": "orecchini",
            "description": "Orecchini eleganti per ogni occasione.",
            "sort_order": 3,
        },
        {
            "name": "Bracciali",
            "slug": "bracciali",
            "description": "Bracciali raffinati in metalli preziosi.",
            "sort_order": 4,
        },
    ],
    "products": [
        # ── Anelli ──
        {
            "category_slug": "anelli",
            "name": "Infinity Mini",
            "slug": "infinity-mini",
            "description": (
                "Un anello delicato con il simbolo dell'infinito, "
                "realizzato a mano in Italia. Il design minimal lo rende "
                "perfetto per l'uso quotidiano."
            ),
            "base_price": "189.00",
            "metal": "gold",
            "gem": "none",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "50", "stock": 5},
                {"metal": "gold", "size": "52", "stock": 8},
                {"metal": "gold", "size": "54", "stock": 3},
                {"metal": "rose", "size": "50", "stock": 4},
                {"metal": "rose", "size": "52", "stock": 6},
                {"metal": "silver", "size": "50", "stock": 12},
                {"metal": "silver", "size": "52", "stock": 10},
                {"metal": "silver", "size": "54", "stock": 8},
            ],
        },
        {
            "category_slug": "anelli",
            "name": "Eternity Band Diamanti",
            "slug": "eternity-band-diamanti",
            "description": (
                "Fascia eternity con diamanti taglio brillante incastonati "
                "su tutto il giro. Un classico intramontabile."
            ),
            "base_price": "1250.00",
            "metal": "gold",
            "gem": "diamond",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "50", "stock": 2},
                {"metal": "gold", "size": "52", "stock": 3},
                {"metal": "rose", "size": "52", "stock": 2},
            ],
        },
        {
            "category_slug": "anelli",
            "name": "Solitario Smeraldo",
            "slug": "solitario-smeraldo",
            "description": (
                "Anello solitario con smeraldo colombiano taglio ovale. "
                "Montatura a griffe in oro 18K."
            ),
            "base_price": "2400.00",
            "metal": "gold",
            "gem": "emerald",
            "purity": "18K",
            "is_featured": False,
            "variants": [
                {"metal": "gold", "size": "50", "stock": 1},
                {"metal": "gold", "size": "52", "stock": 1},
                {"metal": "gold", "size": "54", "stock": 0},  # Coming soon
            ],
        },
        {
            "category_slug": "anelli",
            "name": "Trilogy Classico",
            "slug": "trilogy-classico",
            "description": (
                "Tre diamanti taglio brillante rappresentano passato, "
                "presente e futuro. Design essenziale ed elegante."
            ),
            "base_price": "1890.00",
            "metal": "gold",
            "gem": "diamond",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "50", "stock": 2},
                {"metal": "gold", "size": "52", "stock": 4},
                {"metal": "gold", "size": "54", "stock": 2},
                {"metal": "rose", "size": "52", "stock": 1},
            ],
        },
        # ── Collane ──
        {
            "category_slug": "collane",
            "name": "Catena Veneziana",
            "slug": "catena-veneziana",
            "description": (
                "Collana a catena veneziana, perfetta da sola o con un "
                "pendente. Lunghezza regolabile 42-45 cm."
            ),
            "base_price": "320.00",
            "metal": "gold",
            "gem": "none",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "42cm", "stock": 10},
                {"metal": "gold", "size": "45cm", "stock": 8},
                {"metal": "rose", "size": "42cm", "stock": 5},
                {"metal": "silver", "size": "42cm", "stock": 15},
                {"metal": "silver", "size": "45cm", "stock": 12},
            ],
        },
        {
            "category_slug": "collane",
            "name": "Pendente Goccia Rubino",
            "slug": "pendente-goccia-rubino",
            "description": (
                "Pendente a goccia con rubino naturale birmano, "
                "contornato da un alone di diamanti micro-pavé."
            ),
            "base_price": "3200.00",
            "metal": "gold",
            "gem": "ruby",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "Unica", "stock": 2},
                {"metal": "rose", "size": "Unica", "stock": 1},
            ],
        },
        {
            "category_slug": "collane",
            "name": "Riviera Zaffiri",
            "slug": "riviera-zaffiri",
            "description": (
                "Collana riviera con zaffiri blu ceylon degradé. "
                "Un pezzo unico per serate speciali."
            ),
            "base_price": "4800.00",
            "metal": "gold",
            "gem": "sapphire",
            "purity": "18K",
            "is_featured": False,
            "variants": [
                {"metal": "gold", "size": "Unica", "stock": 1},
            ],
        },
        # ── Orecchini ──
        {
            "category_slug": "orecchini",
            "name": "Cerchi Lucidi Piccoli",
            "slug": "cerchi-lucidi-piccoli",
            "description": (
                "Orecchini a cerchio in oro lucido, diametro 15mm. "
                "Un essenziale del guardaroba."
            ),
            "base_price": "245.00",
            "metal": "gold",
            "gem": "none",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "Unica", "stock": 15},
                {"metal": "rose", "size": "Unica", "stock": 10},
                {"metal": "silver", "size": "Unica", "stock": 20},
            ],
        },
        {
            "category_slug": "orecchini",
            "name": "Punto Luce Diamante",
            "slug": "punto-luce-diamante",
            "description": (
                "Orecchini punto luce con diamanti 0.10ct ciascuno. "
                "Montatura a griffe in oro bianco."
            ),
            "base_price": "890.00",
            "metal": "gold",
            "gem": "diamond",
            "purity": "18K",
            "is_featured": False,
            "variants": [
                {"metal": "gold", "size": "Unica", "stock": 4},
                {"metal": "rose", "size": "Unica", "stock": 3},
            ],
        },
        # ── Bracciali ──
        {
            "category_slug": "bracciali",
            "name": "Tennis Diamanti",
            "slug": "tennis-diamanti",
            "description": (
                "Bracciale tennis con 40 diamanti taglio brillante. "
                "La chiusura di sicurezza garantisce comfort e sicurezza."
            ),
            "base_price": "5500.00",
            "metal": "gold",
            "gem": "diamond",
            "purity": "18K",
            "is_featured": True,
            "variants": [
                {"metal": "gold", "size": "17cm", "stock": 1},
                {"metal": "gold", "size": "19cm", "stock": 2},
                {"metal": "rose", "size": "17cm", "stock": 0},  # Coming soon
            ],
        },
        {
            "category_slug": "bracciali",
            "name": "Maglia Grumetta",
            "slug": "maglia-grumetta",
            "description": (
                "Bracciale a maglia grumetta in argento 925. "
                "Design audace e contemporaneo."
            ),
            "base_price": "175.00",
            "metal": "silver",
            "gem": "none",
            "purity": "925",
            "is_featured": False,
            "variants": [
                {"metal": "silver", "size": "18cm", "stock": 8},
                {"metal": "silver", "size": "20cm", "stock": 6},
            ],
        },
    ],
}


class Command(BaseCommand):
    help = (
        "Seed the database with sample GLORYBELLE products for development. "
        "Do NOT run in production."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete all existing catalog data before seeding.",
        )

    def handle(self, *args, **options):
        if options["flush"]:
            self.stdout.write(self.style.WARNING("Flushing existing catalog data..."))
            ProductImage.objects.all().delete()
            ProductVariant.objects.all().delete()
            Product.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Catalog data flushed."))

        self.stdout.write("Seeding categories...")
        categories = {}
        for cat_data in SEED_DATA["categories"]:
            cat, created = Category.objects.get_or_create(
                slug=cat_data["slug"],
                defaults=cat_data,
            )
            categories[cat.slug] = cat
            status = "CREATED" if created else "EXISTS"
            self.stdout.write(f"  {status}: {cat.name}")

        self.stdout.write("\nSeeding products...")
        product_count = 0
        variant_count = 0

        for prod_data in SEED_DATA["products"]:
            category = categories[prod_data["category_slug"]]
            variants_data = prod_data.pop("variants")
            category_slug = prod_data.pop("category_slug")

            product, created = Product.objects.get_or_create(
                slug=prod_data["slug"],
                defaults={
                    **prod_data,
                    "category": category,
                },
            )

            if created:
                product_count += 1
                self.stdout.write(
                    f"  CREATED: {product.name} ({category.name})"
                )
            else:
                self.stdout.write(
                    f"  EXISTS:  {product.name} ({category.name})"
                )

            # Restore popped keys for idempotency
            prod_data["variants"] = variants_data
            prod_data["category_slug"] = category_slug

            # Create variants
            for var_data in variants_data:
                sku = (
                    f"GB-{product.slug[:8].upper()}-"
                    f"{var_data['metal'][:3].upper()}-"
                    f"{var_data['size'].replace('cm', '')}"
                )
                variant, v_created = ProductVariant.objects.get_or_create(
                    product=product,
                    metal=var_data["metal"],
                    size=var_data["size"],
                    defaults={
                        "sku": sku,
                        "stock_quantity": var_data["stock"],
                    },
                )
                if v_created:
                    variant_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Seed complete: {product_count} products, "
                f"{variant_count} variants created."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "\nNOTE: No images seeded. Add product images through "
                "Django admin: /admin/catalog/product/"
            )
        )
