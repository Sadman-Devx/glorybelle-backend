"""Guest order confirmation lookup (POST /api/orders/lookup/)."""
import pytest

from apps.orders.models import Order

pytestmark = pytest.mark.django_db
URL = "/api/orders/lookup/"


@pytest.fixture
def order(db):
    return Order.objects.create(
        order_number="GB-20260101-TEST", email="Guest@Example.com", status="paid",
        shipping_first_name="A", shipping_last_name="B", shipping_line1="x",
        shipping_city="x", shipping_province="MI", shipping_postal_code="20100",
        billing_first_name="A", billing_last_name="B", billing_line1="x",
        billing_city="x", billing_province="MI", billing_postal_code="20100",
        subtotal="100.00", total="100.00",
    )


def test_guest_can_read_own_order(api_client, order):
    r = api_client.post(URL, {"order_number": "GB-20260101-TEST", "email": "guest@example.com"}, format="json")
    assert r.status_code == 200
    assert r.data["order_number"] == "GB-20260101-TEST"
    assert r.data["status"] == "paid"


def test_wrong_email_is_404(api_client, order):
    r = api_client.post(URL, {"order_number": "GB-20260101-TEST", "email": "other@example.com"}, format="json")
    assert r.status_code == 404


def test_unknown_order_is_same_404(api_client, order):
    wrong_email = api_client.post(URL, {"order_number": "GB-20260101-TEST", "email": "x@example.com"}, format="json")
    unknown = api_client.post(URL, {"order_number": "GB-NOPE", "email": "guest@example.com"}, format="json")
    assert unknown.status_code == 404
    assert unknown.data == wrong_email.data  # order numbers cannot be probed


def test_missing_fields_400(api_client):
    assert api_client.post(URL, {"order_number": "X"}, format="json").status_code == 400
    assert api_client.post(URL, {"email": "a@b.com"}, format="json").status_code == 400


def test_lookup_route_not_shadowed_by_order_detail(api_client):
    # GET must not be captured by orders/<order_number>/ (would be 401, not 405)
    assert api_client.get(URL).status_code == 405
