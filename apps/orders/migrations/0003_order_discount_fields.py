"""
Add discount_percent + discount_amount fields to Order for first-purchase discount.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_order_idempotency_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="discount_percent",
            field=models.DecimalField(
                decimal_places=2,
                default="0.00",
                help_text="Percentuale di sconto applicata (es. 10.00 per 10%).",
                max_digits=5,
                verbose_name="Percentuale sconto",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default="0.00",
                help_text="Importo dello sconto in euro.",
                max_digits=10,
                verbose_name="Importo sconto",
            ),
        ),
    ]
