"""
P1 fix #17 — Add Wishlist parent model per backend-design PDF §2.

Creates the Wishlist table and adds a nullable `wishlist` FK on WishlistItem
(backwards-compatible — existing rows get a Wishlist auto-created via RunPython).
"""
from django.conf import settings
from django.db import migrations, models


def create_wishlists_for_existing_items(apps, schema_editor):
    """For every distinct user in WishlistItem, create a Wishlist and link."""
    Wishlist = apps.get_model("wishlist", "Wishlist")
    WishlistItem = apps.get_model("wishlist", "WishlistItem")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    for user in User.objects.filter(wishlist_items__isnull=False).distinct():
        wishlist, _ = Wishlist.objects.get_or_create(user=user)
        WishlistItem.objects.filter(user=user, wishlist__isnull=True).update(
            wishlist=wishlist
        )


def remove_wishlists(apps, schema_editor):
    """Reverse: delete all Wishlist rows (WishlistItem.wishlist becomes null)."""
    Wishlist = apps.get_model("wishlist", "Wishlist")
    Wishlist.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("wishlist", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Wishlist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creato il")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Aggiornato il")),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="wishlist", to=settings.AUTH_USER_MODEL, verbose_name="Utente")),
            ],
            options={
                "verbose_name": "Lista desideri",
                "verbose_name_plural": "Liste desideri",
            },
        ),
        migrations.AddField(
            model_name="wishlistitem",
            name="wishlist",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="items",
                to="wishlist.wishlist",
                verbose_name="Lista desideri",
            ),
        ),
        migrations.RunPython(create_wishlists_for_existing_items, remove_wishlists),
    ]
