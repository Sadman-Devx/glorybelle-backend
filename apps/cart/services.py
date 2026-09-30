"""
GLORYBELLE — Cart Services.

THIS IS THE CRITICAL FILE — all stock logic lives here.

Per rule.md:
  - "Avoid business logic in views.py"
  - "Never touch stock_quantity or reserved_quantity outside
    select_for_update() inside transaction.atomic()"
  - "Avoid save() without update_fields=[...] when only one or two fields changed"

Per architecture.md §1.3:
  - Add to cart → transaction.atomic() → select_for_update() on variant
  - Check real availability (stock − reserved)
  - Create 15-minute StockReservation
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import ProductVariant
from core.exceptions import OutOfStock

from .models import Cart, CartItem, StockReservation

logger = logging.getLogger(__name__)

RESERVATION_MINUTES = getattr(settings, "STOCK_RESERVATION_MINUTES", 15)


def get_or_create_cart(user=None, session_key=None):
    """
    Get or create a cart for the given user or guest session.

    Priority: user cart > session cart > new cart.
    """
    if user and user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart
    elif session_key:
        cart, _ = Cart.objects.get_or_create(session_key=session_key)
        return cart
    else:
        raise ValueError("Either user or session_key must be provided.")


def add_to_cart(cart, variant_id, quantity=1):
    """
    Add a product variant to the cart with stock reservation.

    CRITICAL: Uses select_for_update() to prevent race conditions.

    Flow:
    1. Lock the variant row
    2. Check real availability (stock - reserved >= requested)
    3. Create/update CartItem
    4. Create StockReservation with 15-min expiry
    5. Increment variant.reserved_quantity

    Raises OutOfStock if insufficient stock.
    """
    with transaction.atomic():
        # Step 1: Lock the variant row to prevent concurrent modification
        variant = (
            ProductVariant.objects.select_for_update()
            .get(id=variant_id, is_active=True)
        )

        # Step 2: Check real availability
        available = variant.stock_quantity - variant.reserved_quantity
        if available < quantity:
            raise OutOfStock(
                detail=(
                    f'"{variant.product.name}" ({variant.get_metal_display()}, '
                    f"misura {variant.size}) non è disponibile nella quantità "
                    f"richiesta. Disponibili: {available}."
                )
            )

        # Step 3: Create or update CartItem
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant=variant,
            defaults={"quantity": quantity},
        )

        if not created:
            # Existing item — check additional quantity is available
            additional = quantity
            if available < additional:
                raise OutOfStock()
            cart_item.quantity += additional
            cart_item.save(update_fields=["quantity", "updated_at"])

        # Step 4: Create StockReservation
        expires_at = timezone.now() + timedelta(minutes=RESERVATION_MINUTES)
        StockReservation.objects.create(
            cart_item=cart_item,
            variant=variant,
            quantity=quantity,
            expires_at=expires_at,
            is_active=True,
        )

        # Step 5: Increment reserved_quantity (minimal write per rule.md)
        variant.reserved_quantity += quantity
        variant.save(update_fields=["reserved_quantity"])

        logger.info(
            "Added %d× %s to cart %s (reserved until %s)",
            quantity,
            variant,
            cart,
            expires_at,
        )

    return cart_item


def remove_from_cart(cart, cart_item_id):
    """
    Remove an item from the cart and release its stock reservation.
    """
    with transaction.atomic():
        try:
            cart_item = CartItem.objects.select_related("variant").get(
                id=cart_item_id, cart=cart
            )
        except CartItem.DoesNotExist:
            return

        # Release all active reservations for this item
        active_reservations = StockReservation.objects.filter(
            cart_item=cart_item, is_active=True
        )
        total_reserved = sum(r.quantity for r in active_reservations)

        if total_reserved > 0:
            variant = (
                ProductVariant.objects.select_for_update()
                .get(id=cart_item.variant_id)
            )
            variant.reserved_quantity = max(
                0, variant.reserved_quantity - total_reserved
            )
            variant.save(update_fields=["reserved_quantity"])

        active_reservations.update(is_active=False)
        cart_item.delete()

        logger.info(
            "Removed item %s from cart %s (released %d reserved)",
            cart_item_id,
            cart,
            total_reserved,
        )


def update_cart_item_quantity(cart, cart_item_id, new_quantity):
    """
    Update the quantity of a cart item.

    If new_quantity > current: reserve additional stock.
    If new_quantity < current: release excess reservation.
    If new_quantity == 0: remove the item entirely.
    """
    if new_quantity <= 0:
        return remove_from_cart(cart, cart_item_id)

    with transaction.atomic():
        cart_item = CartItem.objects.select_related("variant").get(
            id=cart_item_id, cart=cart
        )
        current_qty = cart_item.quantity
        delta = new_quantity - current_qty

        if delta == 0:
            return cart_item

        variant = (
            ProductVariant.objects.select_for_update()
            .get(id=cart_item.variant_id)
        )

        if delta > 0:
            # Need more stock — check availability
            available = variant.stock_quantity - variant.reserved_quantity
            if available < delta:
                raise OutOfStock()

            # Create new reservation for the additional quantity
            expires_at = timezone.now() + timedelta(minutes=RESERVATION_MINUTES)
            StockReservation.objects.create(
                cart_item=cart_item,
                variant=variant,
                quantity=delta,
                expires_at=expires_at,
                is_active=True,
            )
            variant.reserved_quantity += delta
        else:
            # Releasing stock — deactivate excess reservations
            to_release = abs(delta)
            reservations = StockReservation.objects.filter(
                cart_item=cart_item, is_active=True
            ).order_by("-created_at")

            released = 0
            for reservation in reservations:
                if released >= to_release:
                    break
                release_qty = min(reservation.quantity, to_release - released)
                if release_qty == reservation.quantity:
                    reservation.is_active = False
                    reservation.save(update_fields=["is_active"])
                else:
                    reservation.quantity -= release_qty
                    reservation.save(update_fields=["quantity"])
                released += release_qty

            variant.reserved_quantity = max(
                0, variant.reserved_quantity - released
            )

        variant.save(update_fields=["reserved_quantity"])
        cart_item.quantity = new_quantity
        cart_item.save(update_fields=["quantity", "updated_at"])

    return cart_item


def merge_carts(session_key, user):
    """
    Merge a guest cart into the user's cart on login.

    Per PRD §3.3: persistent cart — guest session + logged-in, merged on login.
    """
    try:
        guest_cart = Cart.objects.get(session_key=session_key, user__isnull=True)
    except Cart.DoesNotExist:
        return

    user_cart = get_or_create_cart(user=user)

    with transaction.atomic():
        for guest_item in guest_cart.items.select_related("variant"):
            user_item, created = CartItem.objects.get_or_create(
                cart=user_cart,
                variant=guest_item.variant,
                defaults={"quantity": guest_item.quantity},
            )
            if not created:
                user_item.quantity += guest_item.quantity
                user_item.save(update_fields=["quantity", "updated_at"])

            # Transfer reservations
            StockReservation.objects.filter(
                cart_item=guest_item, is_active=True
            ).update(cart_item=user_item)

        # Delete the now-empty guest cart
        guest_cart.delete()

    logger.info("Merged guest cart (session=%s) into user cart (%s)", session_key, user)
