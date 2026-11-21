"""
P1 fix #8 — Add idempotency_key to Order per backend-design PDF §6.3.

Generated for Django 5.1.x (matches requirements/base.txt pin).
"""
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="idempotency_key",
            field=models.CharField(
                default=uuid.uuid4,
                db_index=True,
                editable=False,
                help_text=(
                    "UUID generato lato client per ogni tentativo di checkout. "
                    "Retries con la stessa chiave restituiscono lo stesso ordine."
                ),
                max_length=64,
                unique=True,
                verbose_name="Chiave idempotenza",
            ),
        ),
    ]
