"""
GLORYBELLE — Catalog Tests.
"""
import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductImage, ProductVariant


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli")


@pytest.fixture
def product_with_variants(category):
    product = Product.objects.create(
        category=category,
        name="Infinity Mini",
        slug="infinity-mini",
        description="Anello minimal in oro 18K.",
        base_price="149.00",
        metal="gold",
        purity="18K",
        is_active=True,
        is_featured=True,
    )
    # Gold variant with stock
    ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="INF-MINI-GOLD-52",
        stock_quantity=10,
    )
    # Silver variant with stock
    ProductVariant.objects.create(
        product=product,
        metal="silver",
        size="52",
        sku="INF-MINI-SILVER-52",
        price_override="99.00",
        stock_quantity=5,
    )
    # Rose variant with ZERO stock (coming soon test case)
    ProductVariant.objects.create(
        product=product,
        metal="rose",
        size="52",
        sku="INF-MINI-ROSE-52",
        stock_quantity=0,
    )
    return product


@pytest.mark.django_db
class TestCategoryAPI:
    def test_list_categories(self, api_client, category):
        url = reverse("category-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["slug"] == "anelli"

    def test_retrieve_category(self, api_client, category):
        url = reverse("category-detail", kwargs={"slug": "anelli"})
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["name"] == "Anelli"


@pytest.mark.django_db
class TestProductAPI:
    def test_list_products(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_category(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url, {"category": "anelli"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_metal(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url, {"metal": "gold"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_by_price_range(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url, {"min_price": 100, "max_price": 200})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_filter_featured(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url, {"featured": "true"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_retrieve_product_detail(self, api_client, product_with_variants):
        url = reverse("product-detail", kwargs={"slug": "infinity-mini"})
        response = api_client.get(url)
        assert response.status_code == 200
        assert response.data["name"] == "Infinity Mini"
        assert len(response.data["variants"]) == 3

    def test_available_metals_excludes_zero_stock(
        self, api_client, product_with_variants
    ):
        """Rose variant has 0 stock — should not appear in available_metals."""
        url = reverse("product-list")
        response = api_client.get(url)
        product_data = response.data["results"][0]
        assert "gold" in product_data["available_metals"]
        assert "silver" in product_data["available_metals"]
        assert "rose" not in product_data["available_metals"]

    def test_empty_filter_returns_empty(self, api_client, product_with_variants):
        url = reverse("product-list")
        response = api_client.get(url, {"category": "nonexistent"})
        assert response.status_code == 200
        assert len(response.data["results"]) == 0
