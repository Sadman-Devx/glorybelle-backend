import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.catalog.models import ProductVariant
from apps.orders.models import Order, OrderAdminNote, OrderItem
from apps.payments.models import Payment
ORDERS_URL = "/api/admin/orders/"
DASHBOARD_URL = "/api/admin/dashboard/"
EXPECTED_TRANSITIONS = {
    "pending": set(),
    "paid": {"processing", "shipped"},
    "processing": {"shipped"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
    "refunded": set(),
}


def make_order(status="pending", user=None):
    return Order.objects.create(
        order_number=f"GB-TEST-{uuid.uuid4().hex[:10].upper()}",
        user=user,
        email="cliente@glorybelle.it",
        status=status,
        shipping_first_name="Giulia",
        shipping_last_name="Bianchi",
        shipping_line1="Via Roma 12",
        shipping_city="Milano",
        shipping_province="MI",
        shipping_postal_code="20121",
        shipping_country="IT",
        billing_first_name="Giulia",
        billing_last_name="Bianchi",
        billing_line1="Via Roma 12",
        billing_city="Milano",
        billing_province="MI",
        billing_postal_code="20121",
        billing_country="IT",
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
    )


@pytest.fixture
def admin_users(db):
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    viewer_group, _ = Group.objects.get_or_create(name="Viewer")
    manager = User.objects.create_user(
        username="orders-manager",
        email="manager-orders@glorybelle.it",
        password="ManagerPass123!",
        is_staff=True,
    )
    manager.groups.add(manager_group)
    viewer = User.objects.create_user(
        username="orders-viewer",
        email="viewer-orders@glorybelle.it",
        password="ViewerPass123!",
        is_staff=True,
    )
    viewer.groups.add(viewer_group)
    customer = User.objects.create_user(
        username="orders-customer",
        email="customer-orders@glorybelle.it",
        password="CustomerPass123!",
    )
    superuser = User.objects.create_superuser(
        username="orders-root",
        email="root-orders@glorybelle.it",
        password="RootPass123!",
    )
    return {
        "manager": manager,
        "viewer": viewer,
        "customer": customer,
        "superuser": superuser,
    }


def authenticated_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "endpoint",
    [
        ORDERS_URL,
        DASHBOARD_URL,
        "/api/admin/orders/{pk}/",
        "/api/admin/orders/{pk}/history/",
        "/api/admin/orders/{pk}/notes/",
    ],
)
def test_order_read_routes_permission_matrix(endpoint, admin_users):
    order = make_order()
    url = endpoint.format(pk=order.pk)

    assert APIClient().get(url).status_code == 401
    assert authenticated_client(admin_users["customer"]).get(url).status_code == 403
    assert authenticated_client(admin_users["viewer"]).get(url).status_code == 200
    assert authenticated_client(admin_users["manager"]).get(url).status_code == 200
    assert authenticated_client(admin_users["superuser"]).get(url).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route", "initial_status", "payload"),
    [
        ("transition", "paid", {"status": "processing"}),
        ("cancel", "pending", {"reason": "Richiesta del cliente"}),
        ("archive", "pending", {"reason": "Ordine concluso"}),
        ("notes", "pending", {"body": "Contattare il cliente"}),
    ],
)
def test_order_write_routes_permission_matrix(
    route, initial_status, payload, admin_users
):
    anonymous_order = make_order(status=initial_status)
    assert (
        APIClient()
        .post(f"{ORDERS_URL}{anonymous_order.pk}/{route}/", payload, format="json")
        .status_code
        == 401
    )
    for role, expected_status in (
        ("customer", 403),
        ("viewer", 403),
        ("manager", 200 if route != "notes" else 201),
        ("superuser", 200 if route != "notes" else 201),
    ):
        order = make_order(status=initial_status)
        response = authenticated_client(admin_users[role]).post(
            f"{ORDERS_URL}{order.pk}/{route}/",
            payload,
            format="json",
        )
        assert response.status_code == expected_status


@pytest.mark.django_db
def test_admin_transition_matrix_and_paid_webhook_authority(admin_users):
    client = authenticated_client(admin_users["manager"])
    for current, targets in EXPECTED_TRANSITIONS.items():
        for target, _ in Order.STATUS_CHOICES:
            order = make_order(status=current)
            payload = {"status": target}
            if target == "shipped":
                payload["tracking_number"] = "TRK-IT-123"
            response = client.post(
                f"{ORDERS_URL}{order.pk}/transition/",
                payload,
                format="json",
            )
            if target in targets:
                assert response.status_code == 200, (current, target, response.data)
                order.refresh_from_db()
                assert order.status == target
                assert response.data["status_history"][0]["actor_id"] == admin_users[
                    "manager"
                ].pk
            else:
                assert response.status_code == 409, (current, target, response.data)
                order.refresh_from_db()
                assert order.status == current

    pending = make_order(status="pending")
    forbidden_paid = client.post(
        f"{ORDERS_URL}{pending.pk}/transition/",
        {"status": "paid"},
        format="json",
    )
    assert forbidden_paid.status_code == 409
    assert forbidden_paid.data["error"]["code"] == "order_conflict"


@pytest.mark.django_db
def test_transition_rejects_tracking_number_for_non_shipped_transition(admin_users):
    order = make_order(status="paid")
    response = authenticated_client(admin_users["manager"]).post(
        f"{ORDERS_URL}{order.pk}/transition/",
        {"status": "processing", "tracking_number": "TRK-123"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_paid_order_cancel_refunds_full_validated_amount_idempotently(admin_users):
    order = make_order(status="paid")
    order.stripe_payment_intent_id = "pi_admin_refund"
    order.save(update_fields=["stripe_payment_intent_id"])
    payment = Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_admin_refund",
        amount=order.total,
        currency="EUR",
        status="succeeded",
        idempotency_key="payment-admin-refund",
    )
    stripe_client = SimpleNamespace(Refund=SimpleNamespace(create=Mock()))
    stripe_client.Refund.create.return_value = SimpleNamespace(
        id="re_admin_refund",
        status="succeeded",
        get=lambda key: {
            "id": "re_admin_refund",
            "status": "succeeded",
        }.get(key),
    )

    with patch("admin_api.order_services._get_stripe", return_value=stripe_client):
        response = authenticated_client(admin_users["manager"]).post(
            f"{ORDERS_URL}{order.pk}/cancel/",
            {"reason": "Rimborso richiesto"},
            format="json",
        )

    assert response.status_code == 200
    stripe_client.Refund.create.assert_called_once_with(
        payment_intent="pi_admin_refund",
        amount=10000,
        idempotency_key=f"glorybelle-order-cancel-{order.pk}-refund-v1",
        metadata={"order_number": order.order_number},
    )
    order.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == "cancelled"
    assert Order.objects.filter(pk=order.pk).exists()
    assert payment.status == "refunded"
    assert payment.stripe_refund_id == "re_admin_refund"
    assert response.data["audit_event"]["actor_id"] == admin_users["manager"].pk
    assert response.data["audit_event"]["reason"] == "Rimborso richiesto"

    repeated = authenticated_client(admin_users["manager"]).post(
        f"{ORDERS_URL}{order.pk}/cancel/",
        {"reason": "Rimborso richiesto"},
        format="json",
    )
    assert repeated.status_code == 409
    stripe_client.Refund.create.assert_called_once()


@pytest.mark.django_db
def test_paid_cancel_rejects_payment_amount_mismatch_without_refunding(admin_users):
    order = make_order(status="paid")
    order.stripe_payment_intent_id = "pi_amount_mismatch"
    order.save(update_fields=["stripe_payment_intent_id"])
    Payment.objects.create(
        order=order,
        stripe_payment_intent_id="pi_amount_mismatch",
        amount=Decimal("99.00"),
        currency="EUR",
        status="succeeded",
        idempotency_key="payment-amount-mismatch",
    )

    with patch("admin_api.order_services._get_stripe") as stripe_factory:
        response = authenticated_client(admin_users["manager"]).post(
            f"{ORDERS_URL}{order.pk}/cancel/",
            {"reason": "Importo da verificare"},
            format="json",
        )

    assert response.status_code == 409
    stripe_factory.assert_not_called()
    order.refresh_from_db()
    assert order.status == "paid"


@pytest.mark.django_db
def test_cancel_pending_order_preserves_row_and_requires_reason(admin_users):
    order = make_order()
    client = authenticated_client(admin_users["manager"])
    missing_reason = client.post(
        f"{ORDERS_URL}{order.pk}/cancel/",
        {},
        format="json",
    )
    assert missing_reason.status_code == 400

    response = client.post(
        f"{ORDERS_URL}{order.pk}/cancel/",
        {"reason": "Pagamento non completato"},
        format="json",
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert Order.objects.filter(pk=order.pk).exists()
    assert response.data["audit_event"]["reason"] == "Pagamento non completato"


@pytest.mark.django_db
@pytest.mark.parametrize("order_status", ["shipped", "delivered", "refunded"])
def test_fulfilled_or_refunded_orders_cannot_be_cancelled(order_status, admin_users):
    order = make_order(status=order_status)
    response = authenticated_client(admin_users["manager"]).post(
        f"{ORDERS_URL}{order.pk}/cancel/",
        {"reason": "Richiesta non consentita"},
        format="json",
    )
    assert response.status_code == 409
    order.refresh_from_db()
    assert order.status == order_status


@pytest.mark.django_db
def test_archive_is_soft_and_hidden_from_default_list(admin_users):
    order = make_order()
    client = authenticated_client(admin_users["manager"])

    response = client.post(
        f"{ORDERS_URL}{order.pk}/archive/",
        {"reason": "Ordine conservato per archivio"},
        format="json",
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.archived_at is not None
    assert order.archive_reason == "Ordine conservato per archivio"
    assert Order.objects.filter(pk=order.pk).exists()
    assert client.get(ORDERS_URL).data["count"] == 0
    assert client.get(ORDERS_URL, {"include_archived": "true"}).data["count"] == 1
    assert response.data["audit_event"]["actor_id"] == admin_users["manager"].pk


@pytest.mark.django_db
def test_order_list_filters_compact_results_and_detail(admin_users, shared_variant):
    included = make_order()
    excluded = make_order()
    OrderItem.objects.create(
        order=included,
        variant=shared_variant,
        product_name="Anello artigianale",
        variant_metal="gold",
        variant_metal_display="Oro 18K",
        variant_size="52",
        sku=shared_variant.sku,
        unit_price=Decimal("100.00"),
        quantity=1,
        line_total=Decimal("100.00"),
    )
    client = authenticated_client(admin_users["viewer"])
    response = client.get(
        ORDERS_URL,
        {
            "status": "pending",
            "email": "cliente@glorybelle.it",
            "order_number": included.order_number,
            "total_min": "99.99",
            "total_max": "100.00",
            "created_after": (included.created_at - timedelta(hours=1)).isoformat(),
            "created_before": (included.created_at + timedelta(hours=1)).isoformat(),
            "search": "Giulia",
            "ordering": "total",
        },
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    compact = response.data["results"][0]
    assert compact["number"] == included.order_number
    assert compact["customer"]["email"] == included.email
    assert compact["item_count"] == 1

    detail = client.get(f"{ORDERS_URL}{included.pk}/")
    assert detail.status_code == 200
    assert detail.data["items"][0]["product_name"] == "Anello artigianale"
    assert detail.data["shipping_address"]["city"] == "Milano"
    assert detail.data["payment"] is None
    assert detail.data["status_history"]
    assert Order.objects.filter(pk=excluded.pk).exists()


@pytest.mark.django_db
def test_internal_notes_are_manager_written_and_not_customer_order_notes(admin_users):
    order = make_order(user=admin_users["customer"])
    manager = authenticated_client(admin_users["manager"])
    response = manager.post(
        f"{ORDERS_URL}{order.pk}/notes/",
        {"body": "Richiamare domani"},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["author_id"] == admin_users["manager"].pk
    assert OrderAdminNote.objects.filter(order=order, author=admin_users["manager"]).exists()

    detail = authenticated_client(admin_users["viewer"]).get(f"{ORDERS_URL}{order.pk}/")
    assert detail.data["internal_notes"][0]["body"] == "Richiamare domani"

    from apps.orders.serializers import OrderSerializer

    order.refresh_from_db()
    customer_data = OrderSerializer(order).data
    assert "internal_notes" not in customer_data
    assert "Richiamare domani" not in str(customer_data)


@pytest.mark.django_db
def test_dashboard_computes_revenue_stock_and_caches_for_60_seconds(
    admin_users, shared_variant
):
    cache.clear()
    recent = make_order(status="paid")
    older = make_order(status="paid")
    Payment.objects.create(
        order=recent,
        stripe_payment_intent_id=f"pi-{uuid.uuid4().hex}",
        amount=recent.total,
        currency="EUR",
        status="succeeded",
        idempotency_key=f"key-{uuid.uuid4().hex}",
    )
    Payment.objects.create(
        order=older,
        stripe_payment_intent_id=f"pi-{uuid.uuid4().hex}",
        amount=Decimal("50.00"),
        currency="EUR",
        status="succeeded",
        idempotency_key=f"key-{uuid.uuid4().hex}",
    )
    Order.objects.filter(pk=recent.pk).update(
        created_at=timezone.now() - timedelta(days=3)
    )
    Order.objects.filter(pk=older.pk).update(
        created_at=timezone.now() - timedelta(days=14)
    )
    ProductVariant.objects.filter(pk=shared_variant.pk).update(stock_quantity=3)

    client = authenticated_client(admin_users["viewer"])
    response = client.get(DASHBOARD_URL)
    assert response.status_code == 200
    assert response.data["today_orders"] == 0
    assert Decimal(response.data["revenue_last_7_days"]) == Decimal("100.00")
    assert Decimal(response.data["revenue_last_30_days"]) == Decimal("150.00")
    assert response.data["orders_by_status"][1] == {"status": "paid", "count": 2}
    assert response.data["low_stock_variants"][0]["stock_quantity"] == 3

    with patch("admin_api.order_views._dashboard_data", side_effect=AssertionError):
        assert client.get(DASHBOARD_URL).status_code == 200


@pytest.mark.django_db
def test_order_openapi_schema_documents_every_order_endpoint(admin_users):
    response = authenticated_client(admin_users["superuser"]).get("/api/schema/")
    assert response.status_code == 200
    paths = response.data["paths"]
    expected_methods = {
        "/api/admin/dashboard/": {"get"},
        "/api/admin/orders/": {"get"},
        "/api/admin/orders/{id}/": {"get"},
        "/api/admin/orders/{id}/transition/": {"post"},
        "/api/admin/orders/{id}/cancel/": {"post"},
        "/api/admin/orders/{id}/archive/": {"post"},
        "/api/admin/orders/{id}/notes/": {"get", "post"},
        "/api/admin/orders/{id}/history/": {"get"},
    }
    for path, methods in expected_methods.items():
        assert methods <= paths[path].keys()
