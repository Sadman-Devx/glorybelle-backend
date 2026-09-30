"""
GLORYBELLE — Cart Abandonment Report.

Per PRD 3.8: admin-visible report comparing carts created vs carts
converted to a paid Order in a given period.

Usage:
    python manage.py cart_abandonment_report                  # Last 7 days
    python manage.py cart_abandonment_report --days 30        # Last 30 days
    python manage.py cart_abandonment_report --days 1         # Today
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.orders.models import Order


class Command(BaseCommand):
    help = "Generate a cart abandonment report for a given period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days to look back (default: 7).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        since = timezone.now() - timedelta(days=days)

        sep = "=" * 51
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(sep))
        self.stdout.write(
            self.style.HTTP_INFO("  GLORYBELLE -- Cart Abandonment Report")
        )
        self.stdout.write(
            self.style.HTTP_INFO(
                f"  Period: last {days} days "
                f"({since.strftime('%Y-%m-%d')} -> "
                f"{timezone.now().strftime('%Y-%m-%d')})"
            )
        )
        self.stdout.write(self.style.HTTP_INFO(sep))
        self.stdout.write("")

        # -- Carts created in period --
        total_carts = Cart.objects.filter(created_at__gte=since).count()
        carts_with_items = (
            Cart.objects.filter(created_at__gte=since)
            .annotate(item_count=Count("items"))
            .filter(item_count__gt=0)
            .count()
        )
        empty_carts = total_carts - carts_with_items

        # -- Orders created in period --
        total_orders = Order.objects.filter(created_at__gte=since).count()
        paid_orders = Order.objects.filter(
            created_at__gte=since, status="paid"
        ).count()
        pending_orders = Order.objects.filter(
            created_at__gte=since, status="pending"
        ).count()
        cancelled_orders = Order.objects.filter(
            created_at__gte=since, status="cancelled"
        ).count()

        # -- Revenue --
        revenue = (
            Order.objects.filter(created_at__gte=since, status="paid")
            .aggregate(total=Sum("total"))
            .get("total")
            or 0
        )

        # -- Abandonment rate --
        if carts_with_items > 0:
            abandonment_rate = (
                (carts_with_items - paid_orders) / carts_with_items * 100
            )
        else:
            abandonment_rate = 0

        conversion_rate = 100 - abandonment_rate if carts_with_items > 0 else 0

        # -- Top abandoned products --
        abandoned_items = (
            CartItem.objects.filter(cart__created_at__gte=since)
            .exclude(cart__user__orders__status="paid")
            .values("variant__product__name")
            .annotate(
                abandon_count=Count("id"),
                total_qty=Sum("quantity"),
            )
            .order_by("-abandon_count")[:5]
        )

        # -- Output --
        self.stdout.write("CART METRICS")
        self.stdout.write(f"  Total carts created:     {total_carts}")
        self.stdout.write(f"  Carts with items:        {carts_with_items}")
        self.stdout.write(f"  Empty carts:             {empty_carts}")
        self.stdout.write("")

        self.stdout.write("ORDER METRICS")
        self.stdout.write(f"  Total orders:            {total_orders}")
        self.stdout.write(
            self.style.SUCCESS(f"  Paid orders:             {paid_orders}")
        )
        self.stdout.write(f"  Pending orders:          {pending_orders}")
        self.stdout.write(
            self.style.WARNING(f"  Cancelled orders:        {cancelled_orders}")
        )
        self.stdout.write("")

        self.stdout.write("REVENUE")
        self.stdout.write(
            self.style.SUCCESS(
                f"  Total revenue (paid):    EUR {revenue:,.2f}"
            )
        )
        self.stdout.write("")

        self.stdout.write("ABANDONMENT")
        if abandonment_rate > 70:
            style = self.style.ERROR
        elif abandonment_rate > 50:
            style = self.style.WARNING
        else:
            style = self.style.SUCCESS
        self.stdout.write(
            style(f"  Abandonment rate:        {abandonment_rate:.1f}%")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"  Conversion rate:         {conversion_rate:.1f}%"
            )
        )
        self.stdout.write("")

        if abandoned_items:
            self.stdout.write("TOP ABANDONED PRODUCTS")
            for item in abandoned_items:
                name = item["variant__product__name"] or "Unknown"
                self.stdout.write(
                    f"  {item['abandon_count']}x abandoned -- {name} "
                    f"({item['total_qty']} units)"
                )
        else:
            self.stdout.write("  No abandoned cart items in this period.")

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(sep))
