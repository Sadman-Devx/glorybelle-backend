"""
GLORYBELLE — Order Services.

THIS IS CRITICAL ORDER LOGIC — all order creation lives here.

Per rule.md:
  - "Avoid business logic in views.py"
  - "Never trust a client-supplied price, subtotal, or total"
  - "Avoid save() without update_fields=[...] when only one or two fields changed"

Per roadmap Day 6:
  - create_order_from_cart() snapshots line items at time of purchase
  - Checkout endpoint creates Order (status=pending)
"""
import logging
import random
import string
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Address
from apps.cart.models import StockReservation
from core.exceptions import CartEmpty, ReservationExpired

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


def generate_order_number():
    """
    Generate a unique order number: GB-YYYYMMDD-XXXX.

    Format matches Italian business conventions. 4-character alphanumeric
    suffix provides enough uniqueness for daily order volume.
    """
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
):
    """
    Create an Order from a Cart, snapshotting all line items.

    Per rule.md: prices are ALWAYS resolved server-side from
    ProductVariant.price_override / Product.base_price — never from
    client-supplied values.

    Args:
        cart: Cart instance
        email: Customer email (required even for guests)
        shipping_address_id: ID of saved Address (for authenticated users)
        shipping_address_data: Dict of address fields (for guest/inline)
        billing_address_id: ID of saved billing Address
        billing_address_data: Dict of billing address fields
        billing_same_as_shipping: If True, copy shipping to billing
        user: User instance (None for guest checkout)
        notes: Optional customer notes

    Returns:
        Order instance with status=pending

    Raises:
        CartEmpty: if cart has no items
        ReservationExpired: if any stock reservation has expired
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
        shipping_addr = Address.objects.get(id=shipping_address_id, user=user)
        shipping = _snapshot_address(shipping_addr)
    elif shipping_address_data:
        shipping = shipping_address_data
    else:
        raise ValueError("Shipping address is required.")

    # Resolve billing address
    if billing_same_as_shipping:
        billing = shipping
    elif billing_address_id and user:
        billing_addr = Address.objects.get(id=billing_address_id, user=user)
        billing = _snapshot_address(billing_addr)
    elif billing_address_data:
        billing = billing_address_data
    else:
        billing = shipping  # Fallback to shipping

    with transaction.atomic():
        # Calculate totals server-side (rule.md: never trust client price)
        subtotal = Decimal("0.00")
        order_items_data = []

        for item in cart_items:
            # Resolve price server-side
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

        # Shipping cost — free shipping for now (can be configured later)
        shipping_cost = Decimal("0.00")
        total = subtotal + shipping_cost

        # Create Order
        order = Order.objects.create(
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
            # Totals
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            total=total,
            notes=notes,
        )

        # Create OrderItems — snapshot data frozen at purchase time
        for item_data in order_items_data:
            OrderItem.objects.create(order=order, **item_data)

        logger.info(
            "Created order %s for %s — %d items, total €%.2f",
            order.order_number,
            email,
            len(order_items_data),
            total,
        )

    return order
