"""
GLORYBELLE — Invoicing Tests.
"""
import pytest
from unittest.mock import patch, MagicMock

from apps.catalog.models import Category, Product, ProductVariant
from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.invoicing.models import Invoice
from apps.invoicing.fattura24_client import _build_invoice_xml
from apps.orders import services as order_services


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-inv-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Invoice Test Ring",
        slug="invoice-test-ring",
        base_price="149.00",
        metal="gold",
    )


@pytest.fixture
def variant(product):
    return ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="INV-TEST-GOLD-52",
        stock_quantity=10,
    )


@pytest.fixture
def paid_order(user, variant):
    cart = Cart.objects.create(user=user)
    cart_services.add_to_cart(cart, variant.id, quantity=1)

    order = order_services.create_order_from_cart(
        cart=cart,
        email="test@glorybelle.it",
        shipping_address_data={
            "first_name": "Francesca",
            "last_name": "Rossi",
            "line1": "Via Roma 42",
            "city": "Milano",
            "province": "MI",
            "postal_code": "20121",
            "country": "IT",
        },
        user=user,
    )
    order.status = "paid"
    order.save(update_fields=["status"])
    return order


@pytest.mark.django_db
class TestInvoiceGeneration:
    def test_build_invoice_xml(self, paid_order):
        xml = _build_invoice_xml(paid_order)
        assert "GLORYBELLE" in xml
        assert paid_order.order_number in xml
        assert "Invoice Test Ring" in xml

    def test_generate_invoice_creates_record(self, paid_order):
        """Test that the Celery task creates an Invoice record."""
        from apps.invoicing.tasks import generate_invoice

        # Call synchronously for testing
        generate_invoice(paid_order.id)

        invoice = Invoice.objects.get(order=paid_order)
        assert invoice.invoice_number == f"FE-{paid_order.order_number}"
        assert invoice.status == "submitted"

    def test_generate_invoice_idempotent(self, paid_order):
        """Calling twice should not create a duplicate invoice."""
        from apps.invoicing.tasks import generate_invoice

        generate_invoice(paid_order.id)
        generate_invoice(paid_order.id)

        assert Invoice.objects.filter(order=paid_order).count() == 1


@pytest.mark.django_db
class TestOrderConfirmationEmail:
    def test_email_logged_when_sendgrid_not_configured(self, paid_order):
        """When SendGrid is not configured, email should be logged."""
        from apps.invoicing.tasks import send_order_confirmation_email

        # Should not raise — just logs
        send_order_confirmation_email(paid_order.id)
