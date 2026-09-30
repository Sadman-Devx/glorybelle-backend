"""
GLORYBELLE — Wishlist Tests.
"""
import pytest
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.wishlist.models import WishlistItem


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-wish-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Wishlist Test Ring",
        slug="wishlist-test-ring",
        base_price="149.00",
    )


@pytest.mark.django_db
class TestWishlistToggle:
    def test_add_to_wishlist(self, authenticated_client, user, product):
        response = authenticated_client.post(
            "/api/wishlist/toggle/",
            {"product_id": product.id},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["wishlisted"] is True
        assert WishlistItem.objects.filter(user=user, product=product).exists()

    def test_remove_from_wishlist(self, authenticated_client, user, product):
        # Add first
        WishlistItem.objects.create(user=user, product=product)

        # Toggle should remove
        response = authenticated_client.post(
            "/api/wishlist/toggle/",
            {"product_id": product.id},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["wishlisted"] is False
        assert not WishlistItem.objects.filter(user=user, product=product).exists()

    def test_toggle_nonexistent_product(self, authenticated_client):
        response = authenticated_client.post(
            "/api/wishlist/toggle/",
            {"product_id": 99999},
            format="json",
        )
        assert response.status_code == 404

    def test_wishlist_requires_auth(self, api_client, product):
        response = api_client.post(
            "/api/wishlist/toggle/",
            {"product_id": product.id},
            format="json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestWishlistList:
    def test_list_own_wishlist(self, authenticated_client, user, product):
        WishlistItem.objects.create(user=user, product=product)

        response = authenticated_client.get("/api/wishlist/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_empty_wishlist(self, authenticated_client):
        response = authenticated_client.get("/api/wishlist/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 0
