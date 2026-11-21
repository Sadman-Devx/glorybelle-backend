"""
GLORYBELLE — Order Services.

P1 fix #8: idempotency_key support.
New feature: first-purchase discount — 10% off for newly registered customers.
"""
import logging
import random
import string
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Address
from apps.cart.models import StockReservation
from core.exceptions import CartEmpty, ReservationExpired

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


def generate_order_number():
    """Generate a unique order number: GB-YYYYMMDD-XXXX."""
    date_part = timezone.now().strftime("%Y%m%d")
    while True:
        suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        order_number = f"GB-{date_part}-{suffix}"
        if not Order.objects.filter(order_number=order_number).exists():
            return order_number


def _snapshot_address(address):
    """Extract address fields into a flat dict for order snapshotting."""
    return {
        "first_name": address.first_name,
        "last_name": address.last_name,
        "line1": address.line1,
        "line2": address.line2,
        "city": address.city,
        "province": address.province,
        "postal_code": address.postal_code,
        "country": address.country,
    }


def is_first_purchase(user) -> bool:
    """
    Check if the user is eligible for the first-purchase discount.

    Eligibility:
    - User is authenticated
    - Has NO prior orders with status in ['paid', 'processing', 'shipped', 'delivered']
      (cancelled/pending/refunded orders don't count — they didn't complete a purchase)

    Note: The CURRENT order being created doesn't exist yet, so it won't show in the query.
    """
    if not user or not user.is_authenticated:
        return False
    completed_statuses = ["paid", "processing", "shipped", "delivered"]
    return not Order.objects.filter(
        user=user, status__in=completed_statuses
    ).exists()


def calculate_discount(subtotal: Decimal, user) -> tuple[Decimal, Decimal]:
    """
    Calculate discount for an order.

    Returns:
        (discount_percent, discount_amount)
    """
    discount_percent = Decimal("0.00")
    discount_amount = Decimal("0.00")

    if not is_first_purchase(user):
        return discount_percent, discount_amount

    min_subtotal = getattr(
        settings, "FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL", Decimal("0.00")
    )
    if subtotal < min_subtotal:
        return discount_percent, discount_amount

    discount_percent = getattr(
        settings, "FIRST_PURCHASE_DISCOUNT_PERCENT", Decimal("10.00")
    )
    discount_amount = (subtotal * discount_percent / Decimal("100")).quantize(
        Decimal("0.01")
    )

    return discount_percent, discount_amount


def create_order_from_cart(
    cart,
    email,
    shipping_address_id=None,
    shipping_address_data=None,
    billing_address_id=None,
    billing_address_data=None,
    billing_same_as_shipping=True,
    user=None,
    notes="",
    idempotency_key=None,
):
    """
    Create an Order from a Cart, snapshotting all line items.

    Applies first-purchase discount automatically if the user is eligible
    (authenticated + no prior completed orders).
    """
    cart_items = cart.items.select_related(
        "variant", "variant__product"
    ).all()

    if not cart_items.exists():
        raise CartEmpty()

    # Validate all reservations are still active
    for item in cart_items:
        active_reservations = StockReservation.objects.filter(
            cart_item=item, is_active=True
        )
        if not active_reservations.exists():
            raise ReservationExpired(
                detail=(
                    f'La riserva per "{item.variant.product.name}" '
                    f"({item.variant.get_metal_display()}, misura {item.variant.size}) "
                    f"è scaduta. Riprova ad aggiungerlo al carrello."
                )
            )

    # Resolve shipping address
    if shipping_address_id and user:
        try:
            shipping_addr = Address.objects.get(id=shipping_address_id, user=user)
        except Address.DoesNotExist:
            raise ValueError(
                f"Indirizzo di spedizione {shipping_address_id} non trovato."
            )
        shipping = _snapshot_address(shipping_addr)
    elif shipping_address_data:
        shipping = shipping_address_data
    else:
        raise ValueError("Shipping address is required.")

    # Resolve billing address
    if billing_same_as_shipping:
        billing = shipping
    elif billing_address_id and user:
        try:
            billing_addr = Address.objects.get(id=billing_address_id, user=user)
        except Address.DoesNotExist:
            raise ValueError(
                f"Indirizzo di fatturazione {billing_address_id} non trovato."
            )
        billing = _snapshot_address(billing_addr)
    elif billing_address_data:
        billing = billing_address_data
    else:
        billing = shipping

    with transaction.atomic():
        # Calculate subtotal server-side (rule.md: never trust client price)
        subtotal = Decimal("0.00")
        order_items_data = []

        for item in cart_items:
            unit_price = item.variant.price
            line_total = unit_price * item.quantity
            subtotal += line_total

            order_items_data.append({
                "variant": item.variant,
                "product_name": item.variant.product.name,
                "variant_metal": item.variant.metal,
                "variant_metal_display": item.variant.get_metal_display(),
                "variant_size": item.variant.size,
                "sku": item.variant.sku,
                "unit_price": unit_price,
                "quantity": item.quantity,
                "line_total": line_total,
            })

        # Calculate discount (NEW — first-purchase 10% off)
        discount_percent, discount_amount = calculate_discount(subtotal, user)

        # Shipping cost — free shipping for now
        shipping_cost = Decimal("0.00")

        # Total = subtotal - discount + shipping
        total = subtotal - discount_amount + shipping_cost

        # Create Order
        order_kwargs = dict(
            order_number=generate_order_number(),
            user=user if user and user.is_authenticated else None,
            email=email,
            status="pending",
            # Shipping
            shipping_first_name=shipping["first_name"],
            shipping_last_name=shipping["last_name"],
            shipping_line1=shipping["line1"],
            shipping_line2=shipping.get("line2", ""),
            shipping_city=shipping["city"],
            shipping_province=shipping["province"],
            shipping_postal_code=shipping["postal_code"],
            shipping_country=shipping.get("country", "IT"),
            # Billing
            billing_first_name=billing["first_name"],
            billing_last_name=billing["last_name"],
            billing_line1=billing["line1"],
            billing_line2=billing.get("line2", ""),
            billing_city=billing["city"],
            billing_province=billing["province"],
            billing_postal_code=billing["postal_code"],
            billing_country=billing.get("country", "IT"),
            # Totals + discount
            subtotal=subtotal,
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            shipping_cost=shipping_cost,
            total=total,
            notes=notes,
        )

        if idempotency_key:
            order_kwargs["idempotency_key"] = str(idempotency_key)

        order = Order.objects.create(**order_kwargs)

        # Create OrderItems
        for item_data in order_items_data:
            OrderItem.objects.create(order=order, **item_data)

        if discount_amount > 0:
            logger.info(
                "Created order %s for %s — %d items, subtotal €%.2f, "
                "first-purchase discount %.2f%% (−€%.2f), total €%.2f",
                order.order_number,
                email,
                len(order_items_data),
                subtotal,
                discount_percent,
                discount_amount,
                total,
            )
        else:
            logger.info(
                "Created order %s for %s — %d items, total €%.2f",
                order.order_number,
                email,
                len(order_items_data),
                total,
            )

    return order
