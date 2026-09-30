"""
GLORYBELLE — Shared Test Fixtures.

factory_boy factories and pytest fixtures used across all test modules.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Unauthenticated DRF API client."""
    return APIClient()


@pytest.fixture
def create_user(db):
    """Factory function to create a user."""

    def _create_user(
        username="testuser",
        email="test@glorybelle.it",
        password="TestPass123!",
        **kwargs,
    ):
        return User.objects.create_user(
            username=username,
            email=email,
            password=password,
            **kwargs,
        )

    return _create_user


@pytest.fixture
def user(create_user):
    """A default test user."""
    return create_user()


@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated as the default test user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_user(db):
    """An admin/staff user."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@glorybelle.it",
        password="AdminPass123!",
    )


@pytest.fixture
def admin_client(api_client, admin_user):
    """API client authenticated as admin."""
    api_client.force_authenticate(user=admin_user)
    return api_client


# ── Shared Catalog Fixtures ──


@pytest.fixture
def shared_category(db):
    """A reusable category fixture."""
    from apps.catalog.models import Category

    return Category.objects.create(name="Anelli", slug="anelli-shared")


@pytest.fixture
def shared_product(shared_category):
    """A reusable product fixture."""
    from apps.catalog.models import Product

    return Product.objects.create(
        category=shared_category,
        name="Shared Test Ring",
        slug="shared-test-ring",
        base_price="149.00",
        metal="gold",
        is_active=True,
    )


@pytest.fixture
def shared_variant(shared_product):
    """A reusable variant with 10 units of stock."""
    from apps.catalog.models import ProductVariant

    return ProductVariant.objects.create(
        product=shared_product,
        metal="gold",
        size="52",
        sku="SHARED-GOLD-52",
        stock_quantity=10,
    )


@pytest.fixture
def shipping_address_data():
    """Standard shipping address data for checkout tests."""
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

