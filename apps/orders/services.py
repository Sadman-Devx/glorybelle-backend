"""
GLORYBELLE — Order Services.

P1 fix #8: idempotency_key support.
New feature: first-purchase discount — 10% off for newly registered customers.
"""
import logging
import random
import string
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Address
from apps.cart.models import StockReservation
from core.exceptions import (
    CartEmpty,
    CheckoutConflict,
    PaymentServiceUnavailable,
    ReservationExpired,
)

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


def _resolve_checkout_addresses(
    user,
    shipping_address_id,
    shipping_address_data,
    billing_address_id,
    billing_address_data,
    billing_same_as_shipping,
):
    if shipping_address_id and user:
        try:
            shipping_addr = Address.objects.get(id=shipping_address_id, user=user)
        except Address.DoesNotExist:
            raise ValidationError(
                {"shipping_address_id": "Indirizzo di spedizione non trovato."}
            )
        shipping = _snapshot_address(shipping_addr)
    elif shipping_address_data:
        shipping = shipping_address_data
    else:
        raise ValidationError(
            {"shipping_address": "È necessario un indirizzo di spedizione."}
        )

    if billing_same_as_shipping:
        billing = shipping
    elif billing_address_id and user:
        try:
            billing_addr = Address.objects.get(id=billing_address_id, user=user)
        except Address.DoesNotExist:
            raise ValidationError(
                {"billing_address_id": "Indirizzo di fatturazione non trovato."}
            )
        billing = _snapshot_address(billing_addr)
    elif billing_address_data:
        billing = billing_address_data
    else:
        billing = shipping

    return shipping, billing


def checkout_matches_order(order, cart, data, user):
    """Compare a pending order with current server-priced cart and checkout data."""
    if order.cart_id != cart.pk:
        return False

    shipping, billing = _resolve_checkout_addresses(
        user=user,
        shipping_address_id=data.get("shipping_address_id"),
        shipping_address_data=data.get("shipping_address"),
        billing_address_id=data.get("billing_address_id"),
        billing_address_data=data.get("billing_address"),
        billing_same_as_shipping=data.get("billing_same_as_shipping", True),
    )

    order_shipping = {
        "first_name": order.shipping_first_name,
        "last_name": order.shipping_last_name,
        "line1": order.shipping_line1,
        "line2": order.shipping_line2,
        "city": order.shipping_city,
        "province": order.shipping_province,
        "postal_code": order.shipping_postal_code,
        "country": order.shipping_country,
    }
    order_billing = {
        "first_name": order.billing_first_name,
        "last_name": order.billing_last_name,
        "line1": order.billing_line1,
        "line2": order.billing_line2,
        "city": order.billing_city,
        "province": order.billing_province,
        "postal_code": order.billing_postal_code,
        "country": order.billing_country,
    }

    cart_items = list(
        cart.items.select_related("variant").order_by("variant_id")
    )
    order_items = list(order.items.order_by("variant_id"))
    return (
        order.email.strip().casefold() == data["email"].strip().casefold()
        and order.notes == data.get("notes", "")
        and order_shipping == shipping
        and order_billing == billing
        and [
            (item.variant_id, item.quantity, item.variant.price)
            for item in cart_items
        ]
        == [
            (item.variant_id, item.quantity, item.unit_price)
            for item in order_items
        ]
    )


def supersede_pending_checkout_order(order):
    """Cancel the old Stripe intent before marking its pending order superseded."""
    from apps.payments.models import Payment
    from apps.payments.stripe_client import (
        PaymentIntentNotCancellable,
        cancel_payment_intent,
    )

    payment = Payment.objects.select_for_update().filter(order=order).first()
    if payment and payment.status in {"succeeded", "refunded"}:
        raise CheckoutConflict(
            "Il pagamento precedente è già stato completato e non può essere sostituito."
        )

    payment_intent_id = (
        payment.stripe_payment_intent_id
        if payment
        else order.stripe_payment_intent_id
    )
    if payment_intent_id and (
        payment is None or payment.status in {"pending", "failed"}
    ):
        try:
            cancel_payment_intent(payment_intent_id)
        except PaymentIntentNotCancellable as exc:
            if exc.retryable:
                raise PaymentServiceUnavailable() from exc
            raise CheckoutConflict(
                "Il pagamento precedente non può essere annullato in sicurezza."
            ) from exc

    if payment and payment.status == "pending":
        payment.status = "failed"
        payment.save(update_fields=["status", "updated_at"])
    StockReservation.objects.filter(order=order, is_active=True).update(order=None)
    order.status = "cancelled"
    order.save(update_fields=["status", "updated_at"])


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


@dataclass(frozen=True)
class FirstPurchaseDiscount:
    """Result of compute_first_purchase_discount()."""

    percent: Decimal
    amount: Decimal
    product_name: str = ""
    unit_price: Decimal = Decimal("0.00")

    @property
    def applies(self) -> bool:
        return self.amount > 0


NO_DISCOUNT = FirstPurchaseDiscount(Decimal("0.00"), Decimal("0.00"))


def compute_first_purchase_discount(lines, user) -> FirstPurchaseDiscount:
    """
    Welcome discount for a newly registered customer.

    Rule: ``FIRST_PURCHASE_DISCOUNT_PERCENT`` (10%) off **ONE product — a single unit of
    the most expensive item in the cart**, never the whole basket. It is granted
    automatically to a signed-in customer who has no completed order yet, and it has NO
    expiry: it is still there a month (or a year) after registering, until the first order
    is actually paid.

    ``lines`` is an iterable of ``(product_name, unit_price, quantity)``. The cart preview
    (GET /api/cart/) and the order creation both call this one function, so the discount
    the customer sees in the cart is exactly the discount that is charged.
    """
    lines = [(name, Decimal(price), qty) for name, price, qty in lines if qty > 0]
    if not lines or not is_first_purchase(user):
        return NO_DISCOUNT

    subtotal = sum((price * qty for _, price, qty in lines), Decimal("0.00"))
    min_subtotal = getattr(
        settings, "FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL", Decimal("0.00")
    )
    if subtotal < min_subtotal:
        return NO_DISCOUNT

    percent = Decimal(
        getattr(settings, "FIRST_PURCHASE_DISCOUNT_PERCENT", Decimal("10.00"))
    )
    # max() returns the FIRST maximal element, so ties go to the item added first
    name, unit_price, _qty = max(lines, key=lambda line: line[1])
    amount = (unit_price * percent / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if amount <= 0:
        return NO_DISCOUNT
    return FirstPurchaseDiscount(percent, amount, name, unit_price)


def _release_first_purchase_discount_holds(user) -> bool:
    """
    Guarantee a user never holds more than ONE open first-purchase-discount order.

    The discount is priced into the Stripe PaymentIntent at checkout, so it
    cannot be taken back afterwards. Without this, a customer could create
    several pending orders (each at 10% off) and pay them all. Before a new
    order may take the discount, any earlier PENDING order of the same user
    that still carries it is superseded: its PaymentIntent is cancelled at
    Stripe FIRST and only then is the order cancelled.

    Returns False when an earlier discounted order cannot be proven cancelled
    (payment already succeeded / processing, or Stripe unreachable). The new
    order is then created WITHOUT the discount — the safe default for money.

    Must run inside transaction.atomic() with the user row locked, so two
    parallel checkouts by one user are serialised.
    """
    from apps.payments.models import Payment
    from apps.payments.stripe_client import (
        PaymentIntentNotCancellable,
        cancel_payment_intent,
    )

    open_orders = Order.objects.select_for_update().filter(
        user=user, status="pending", discount_amount__gt=0
    )
    for old in open_orders:
        payment = Payment.objects.filter(order=old).first()
        if payment is not None and payment.status == "pending":
            try:
                cancel_payment_intent(payment.stripe_payment_intent_id)
            except PaymentIntentNotCancellable as exc:
                if exc.retryable:
                    # Stripe is unreachable: we cannot know whether the earlier
                    # intent is payable. Creating the new PaymentIntent would fail
                    # moments later anyway, so ask the customer to retry instead of
                    # quietly withholding a discount they are entitled to.
                    raise PaymentServiceUnavailable() from exc
                logger.warning(
                    "Order %s still holds the first-purchase discount and its "
                    "PaymentIntent cannot be cancelled — new order gets no discount",
                    old.order_number,
                )
                return False
            payment.status = "failed"
            payment.save(update_fields=["status", "updated_at"])
        old.status = "cancelled"
        old.save(update_fields=["status", "updated_at"])
        logger.info(
            "Order %s superseded by a newer checkout (first-purchase discount moved)",
            old.order_number,
        )
    return True


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

    shipping, billing = _resolve_checkout_addresses(
        user=user,
        shipping_address_id=shipping_address_id,
        shipping_address_data=shipping_address_data,
        billing_address_id=billing_address_id,
        billing_address_data=billing_address_data,
        billing_same_as_shipping=billing_same_as_shipping,
    )

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

        # Calculate discount (first-purchase 10% off) — at most ONE open
        # discounted order per user (see _release_first_purchase_discount_holds).
        discount = NO_DISCOUNT
        if user and user.is_authenticated:
            from django.contrib.auth import get_user_model

            get_user_model().objects.select_for_update().get(pk=user.pk)
            if _release_first_purchase_discount_holds(user):
                discount = compute_first_purchase_discount(
                    [
                        (d["product_name"], d["unit_price"], d["quantity"])
                        for d in order_items_data
                    ],
                    user,
                )
        discount_percent, discount_amount = discount.percent, discount.amount

        # Shipping cost — free shipping for now
        shipping_cost = Decimal("0.00")

        # Total = subtotal - discount + shipping
        total = subtotal - discount_amount + shipping_cost

        # Create Order
        order_kwargs = dict(
            order_number=generate_order_number(),
            cart=cart,
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
            discount_product_name=discount.product_name,
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

        StockReservation.objects.filter(
            cart_item__cart=cart,
            is_active=True,
        ).update(order=order)

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
