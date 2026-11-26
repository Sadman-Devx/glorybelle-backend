"""
Payment -> webhook -> Celery -> SendGrid, end to end, with SendGrid and Fattura24 mocked.
(Celery runs eagerly in the test settings, so the whole chain executes in-process.)
"""
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.cart import services as cart_services
from apps.cart.models import Cart
from apps.catalog.models import Category, Product, ProductVariant
from apps.orders import services as order_services
from apps.payments import services as payment_services
from apps.payments.models import Payment

pytestmark = pytest.mark.django_db
SHIP = {"first_name": "Mario", "last_name": "Rossi", "line1": "Via Roma 1", "city": "Milano",
        "province": "MI", "postal_code": "20100", "country": "IT"}


def _paid_order(user, first_name="Mario", product_name="Anello"):
    cat = Category.objects.create(name="C", slug=f"c-{product_name.lower()[:5]}-{first_name[:3]}")
    prod = Product.objects.create(category=cat, name=product_name, slug=f"p-{abs(hash(product_name + first_name))}",
                                  base_price="100.00", metal="gold")
    var = ProductVariant.objects.create(product=prod, metal="gold", size="12", sku=f"E-{abs(hash(first_name))}", stock_quantity=5)
    cart = Cart.objects.create(user=user)
    cart_services.add_to_cart(cart, var.id, quantity=1)
    order = order_services.create_order_from_cart(
        cart=cart, email="buyer@example.com", shipping_address_data=dict(SHIP, first_name=first_name), user=user,
    )
    Payment.objects.create(order=order, stripe_payment_intent_id="pi_mail", amount=order.total, currency="EUR",
                           status="pending", idempotency_key="k-mail")
    return order


def _event():
    return {"id": "evt_mail", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_mail"}}}


def _html(message):
    return message.get()["content"][0]["value"]


@override_settings(SENDGRID_API_KEY="SG.test-key")
@patch("apps.invoicing.fattura24_client.create_invoice", return_value={"fattura24_id": "F24-1"})
@patch("sendgrid.SendGridAPIClient")
def test_paid_webhook_sends_exactly_one_confirmation_email(sendgrid_cls, _invoice, user):
    order = _paid_order(user)
    assert payment_services.handle_payment_succeeded(_event()) is True

    sendgrid_cls.assert_called_once_with("SG.test-key")
    send = sendgrid_cls.return_value.send
    send.assert_called_once()
    message = send.call_args.args[0]
    body = message.get()
    assert body["personalizations"][0]["to"][0]["email"] == "buyer@example.com"
    assert order.order_number in body["subject"]
    assert order.order_number in _html(message)

    # Stripe re-delivering the same event must not email the customer again
    assert payment_services.handle_payment_succeeded(_event()) is True
    send.assert_called_once()


@override_settings(SENDGRID_API_KEY="SG.test-key")
@patch("apps.invoicing.fattura24_client.create_invoice", return_value={"fattura24_id": "F24-2"})
@patch("sendgrid.SendGridAPIClient")
def test_customer_controlled_text_is_html_escaped_in_the_email(sendgrid_cls, _invoice, user):
    """A guest can order with ANY email address; their name must not inject markup into mail sent from our domain."""
    _paid_order(user, first_name='<a href="http://evil.test">Clicca qui</a>', product_name="<b>x</b>")
    payment_services.handle_payment_succeeded(_event())
    html = _html(sendgrid_cls.return_value.send.call_args.args[0])
    assert "<a href" not in html and "evil.test\"" not in html
    assert "&lt;a href" in html
    assert "<b>x</b>" not in html


@override_settings(SENDGRID_API_KEY="SG.test-key")
@patch("apps.invoicing.fattura24_client.create_invoice", return_value={"fattura24_id": "F24-3"})
@patch("sendgrid.SendGridAPIClient")
def test_sendgrid_outage_never_breaks_the_webhook(sendgrid_cls, _invoice, user):
    sendgrid_cls.return_value.send.side_effect = ConnectionError("sendgrid down")
    order = _paid_order(user)
    assert payment_services.handle_payment_succeeded(_event()) is True   # Stripe must still get a 200
    order.refresh_from_db()
    assert order.status == "paid"
