"""
GLORYBELLE — Cart Tests.

Includes the CRITICAL concurrency test from the roadmap:
"Two simultaneous requests against the last unit of stock results in
exactly one success and one clean OutOfStock — not a negative stock count."
"""
import threading

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TransactionTestCase

from apps.cart import services
from apps.cart.models import Cart, StockReservation
from apps.catalog.models import Category, Product, ProductVariant
from core.exceptions import OutOfStock


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Test Ring",
        slug="test-ring",
        base_price="149.00",
        metal="gold",
    )


@pytest.fixture
def variant_with_stock(product):
    """Variant with 5 units of stock."""
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="TEST-GOLD-52",
        stock_quantity=5,
        reserved_quantity=0,
    )


@pytest.fixture
def variant_last_unit(product):
    """Variant with exactly 1 unit — for concurrency testing."""
    return ProductVariant.objects.create(
        product=product,
        metal="silver",
        size="52",
        sku="TEST-SILVER-52",
        stock_quantity=1,
        reserved_quantity=0,
    )


@pytest.fixture
def user_cart(user):
    return Cart.objects.create(user=user)


@pytest.fixture
def guest_cart():
    return Cart.objects.create(session_key="test-guest-session-123")


@pytest.mark.django_db
class TestAddToCart:
    def test_add_item_success(self, user_cart, variant_with_stock):
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=2)
        assert item.quantity == 2

        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 2

        assert StockReservation.objects.filter(
            cart_item=item, is_active=True
        ).exists()

    def test_add_item_insufficient_stock(self, user_cart, variant_with_stock):
        with pytest.raises(OutOfStock):
            services.add_to_cart(user_cart, variant_with_stock.id, quantity=10)

    def test_add_same_item_twice_increments(self, user_cart, variant_with_stock):
        services.add_to_cart(user_cart, variant_with_stock.id, quantity=1)
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=1)
        assert item.quantity == 2

        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 2

    def test_add_item_zero_stock(self, user_cart, product):
        zero_variant = ProductVariant.objects.create(
            product=product,
            metal="rose",
            size="52",
            sku="TEST-ROSE-52",
            stock_quantity=0,
        )
        with pytest.raises(OutOfStock):
            services.add_to_cart(user_cart, zero_variant.id)


@pytest.mark.django_db
class TestRemoveFromCart:
    def test_remove_releases_reservation(self, user_cart, variant_with_stock):
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=2)
        services.remove_from_cart(user_cart, item.id)

        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 0
        assert not StockReservation.objects.filter(is_active=True).exists()


@pytest.mark.django_db
class TestUpdateQuantity:
    def test_increase_quantity(self, user_cart, variant_with_stock):
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=1)
        updated = services.update_cart_item_quantity(user_cart, item.id, 3)
        assert updated.quantity == 3

        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 3

    def test_decrease_quantity(self, user_cart, variant_with_stock):
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=3)
        updated = services.update_cart_item_quantity(user_cart, item.id, 1)
        assert updated.quantity == 1

        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 1

    def test_set_zero_removes_item(self, user_cart, variant_with_stock):
        item = services.add_to_cart(user_cart, variant_with_stock.id, quantity=2)
        services.update_cart_item_quantity(user_cart, item.id, 0)

        assert user_cart.items.count() == 0
        variant_with_stock.refresh_from_db()
        assert variant_with_stock.reserved_quantity == 0


@pytest.mark.django_db
class TestCartMerge:
    def test_merge_guest_into_user(self, user, variant_with_stock):
        guest_cart = Cart.objects.create(session_key="merge-test-session")
        user_cart = Cart.objects.create(user=user)

        services.add_to_cart(guest_cart, variant_with_stock.id, quantity=2)
        services.merge_carts("merge-test-session", user)

        assert not Cart.objects.filter(session_key="merge-test-session").exists()
        user_cart.refresh_from_db()
        assert user_cart.items.count() == 1
        assert user_cart.items.first().quantity == 2


class TestStockConcurrency(TransactionTestCase):
    """
    CRITICAL CONCURRENCY TEST.

    Per roadmap Day 5:
    "Two simultaneous requests against the last unit of stock results in
    exactly one success and one clean OutOfStock — not a negative stock count.
    This is the test to actually run, not just reason about."

    NOTE: This test requires Postgres (select_for_update). SQLite uses
    table-level locking which causes 'database table is locked' errors
    instead of proper row-level concurrency control.
    """

    @pytest.mark.skipif(
        "sqlite" in str(settings.DATABASES["default"]["ENGINE"]),
        reason="select_for_update requires Postgres, not SQLite",
    )
    def test_concurrent_last_unit(self):
        category = Category.objects.create(name="Test Cat", slug="test-cat-conc")
        product = Product.objects.create(
            category=category,
            name="Concurrency Test Ring",
            slug="concurrency-test-ring",
            base_price="149.00",
        )
        variant = ProductVariant.objects.create(
            product=product,
            metal="gold",
            size="52",
            sku="CONC-GOLD-52",
            stock_quantity=1,
            reserved_quantity=0,
        )

        user1 = User.objects.create_user("user1", "u1@test.it", "pass123!")
        user2 = User.objects.create_user("user2", "u2@test.it", "pass123!")
        cart1 = Cart.objects.create(user=user1)
        cart2 = Cart.objects.create(user=user2)

        results = {"success": 0, "out_of_stock": 0, "errors": []}

        def try_add(cart, name):
            try:
                services.add_to_cart(cart, variant.id, quantity=1)
                results["success"] += 1
            except OutOfStock:
                results["out_of_stock"] += 1
            except Exception as e:
                results["errors"].append(f"{name}: {e}")

        t1 = threading.Thread(target=try_add, args=(cart1, "user1"))
        t2 = threading.Thread(target=try_add, args=(cart2, "user2"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed, one should fail
        self.assertEqual(results["success"], 1, f"Expected 1 success, got {results}")
        self.assertEqual(
            results["out_of_stock"], 1, f"Expected 1 OutOfStock, got {results}"
        )
        self.assertEqual(results["errors"], [], f"Unexpected errors: {results['errors']}")

        # Stock should never go negative
        variant.refresh_from_db()
        self.assertGreaterEqual(variant.reserved_quantity, 0)
        self.assertLessEqual(variant.reserved_quantity, variant.stock_quantity)
