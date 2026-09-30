"""
GLORYBELLE — Order Tests.
"""
import pytest
from decimal import Decimal

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.orders.models import Order, OrderItem
from core.exceptions import CartEmpty, ReservationExpired


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-orders-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Test Ring Orders",
        slug="test-ring-orders",
        base_price="149.00",
        metal="gold",
    )


@pytest.fixture
def variant(product):
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="TEST-ORD-GOLD-52",
        stock_quantity=10,
    )


@pytest.fixture
def variant_silver(product):
    return ProductVariant.objects.create(
        product=product,
        metal="silver",
        size="52",
        sku="TEST-ORD-SILVER-52",
        stock_quantity=5,
        price_override="99.00",
    )


@pytest.fixture
def cart_with_items(user, variant, variant_silver):
    cart = Cart.objects.create(user=user)
    cart_services.add_to_cart(cart, variant.id, quantity=2)
    cart_services.add_to_cart(cart, variant_silver.id, quantity=1)
    return cart


@pytest.fixture
def shipping_address_data():
    return {
        "first_name": "Francesca",
        "last_name": "Rossi",
        "line1": "Via Roma 42",
        "line2": "",
        "city": "Milano",
        "province": "MI",
        "postal_code": "20121",
        "country": "IT",
    }


@pytest.mark.django_db
class TestOrderCreation:
    def test_create_order_from_cart(
        self, cart_with_items, user, shipping_address_data
    ):
        order = order_services.create_order_from_cart(
            cart=cart_with_items,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        assert order.status == "pending"
        assert order.order_number.startswith("GB-")
        assert order.email == "test@glorybelle.it"
        assert order.user == user
        assert order.items.count() == 2

        # Verify totals are server-calculated
        expected_subtotal = Decimal("149.00") * 2 + Decimal("99.00") * 1
        assert order.subtotal == expected_subtotal
        assert order.total == expected_subtotal  # free shipping

    def test_order_snapshots_product_data(
        self, cart_with_items, user, shipping_address_data, variant
    ):
        order = order_services.create_order_from_cart(
            cart=cart_with_items,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        gold_item = order.items.get(variant=variant)
        assert gold_item.product_name == "Test Ring Orders"
        assert gold_item.variant_metal == "gold"
        assert gold_item.sku == "TEST-ORD-GOLD-52"
        assert gold_item.unit_price == Decimal("149.00")
        assert gold_item.quantity == 2
        assert gold_item.line_total == Decimal("298.00")

    def test_order_snapshots_address(
        self, cart_with_items, user, shipping_address_data
    ):
        order = order_services.create_order_from_cart(
            cart=cart_with_items,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        assert order.shipping_first_name == "Francesca"
        assert order.shipping_city == "Milano"
        assert order.shipping_province == "MI"

    def test_empty_cart_raises_error(self, user, shipping_address_data):
        empty_cart = Cart.objects.create(user=user)
        with pytest.raises(CartEmpty):
            order_services.create_order_from_cart(
                cart=empty_cart,
                email="test@glorybelle.it",
                shipping_address_data=shipping_address_data,
                user=user,
            )

    def test_guest_checkout(self, variant, shipping_address_data):
        """Per PRD §3.2: guest checkout — Order without a user."""
        guest_cart = Cart.objects.create(session_key="guest-checkout-test")
        cart_services.add_to_cart(guest_cart, variant.id, quantity=1)

        order = order_services.create_order_from_cart(
            cart=guest_cart,
            email="guest@example.it",
            shipping_address_data=shipping_address_data,
            user=None,
        )

        assert order.user is None
        assert order.email == "guest@example.it"
        assert order.items.count() == 1

    def test_billing_same_as_shipping(
        self, cart_with_items, user, shipping_address_data
    ):
        order = order_services.create_order_from_cart(
            cart=cart_with_items,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            billing_same_as_shipping=True,
            user=user,
        )

        assert order.billing_first_name == order.shipping_first_name
        assert order.billing_city == order.shipping_city

    def test_order_number_unique(
        self, user, variant, shipping_address_data
    ):
        """Generate two orders, verify different order numbers."""
        cart1 = Cart.objects.create(user=user)
        cart_services.add_to_cart(cart1, variant.id, quantity=1)
        order1 = order_services.create_order_from_cart(
            cart=cart1,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        # Need a new cart for second order
        cart2 = Cart.objects.create(session_key="unique-test-session")
        cart_services.add_to_cart(cart2, variant.id, quantity=1)
        order2 = order_services.create_order_from_cart(
            cart=cart2,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
        )

        assert order1.order_number != order2.order_number


@pytest.mark.django_db
class TestOrderAPI:
    def test_order_history_authenticated(
        self, authenticated_client, user, variant, shipping_address_data
    ):
        cart = Cart.objects.create(user=user)
        cart_services.add_to_cart(cart, variant.id, quantity=1)
        order_services.create_order_from_cart(
            cart=cart,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        response = authenticated_client.get("/api/orders/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_order_history_unauthenticated(self, api_client):
        response = api_client.get("/api/orders/")
        assert response.status_code == 401

    def test_order_detail(
        self, authenticated_client, user, variant, shipping_address_data
    ):
        cart = Cart.objects.create(user=user)
        cart_services.add_to_cart(cart, variant.id, quantity=1)
        order = order_services.create_order_from_cart(
            cart=cart,
            email="test@glorybelle.it",
            shipping_address_data=shipping_address_data,
            user=user,
        )

        response = authenticated_client.get(
            f"/api/orders/{order.order_number}/"
        )
        assert response.status_code == 200
        assert response.data["order_number"] == order.order_number
