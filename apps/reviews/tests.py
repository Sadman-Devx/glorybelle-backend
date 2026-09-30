"""
GLORYBELLE — Review Tests.
"""
import pytest

from apps.catalog.models import Category, Product
from apps.reviews.models import Review


@pytest.fixture
def category(db):
    return Category.objects.create(name="Anelli", slug="anelli-rev-test")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Review Test Ring",
        slug="review-test-ring",
        base_price="149.00",
    )


@pytest.mark.django_db
class TestReviewAPI:
    def test_list_approved_reviews(self, api_client, user, product):
        Review.objects.create(
            user=user,
            product=product,
            rating=5,
            title="Bellissimo",
            body="Un anello perfetto.",
            is_approved=True,
        )
        Review.objects.create(
            user=user,
            product=Product.objects.create(
                category=product.category,
                name="Other Ring",
                slug="other-ring",
                base_price="99.00",
            ),
            rating=3,
            title="Pending",
            body="Not yet approved.",
            is_approved=False,
        )

        response = api_client.get(
            f"/api/products/{product.slug}/reviews/"
        )
        assert response.status_code == 200
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["title"] == "Bellissimo"

    def test_create_review(self, authenticated_client, product):
        response = authenticated_client.post(
            f"/api/products/{product.slug}/reviews/create/",
            {
                "rating": 5,
                "title": "Eccezionale",
                "body": "La qualità è straordinaria.",
            },
            format="json",
        )
        assert response.status_code == 201

        # Should be unapproved (moderation queue)
        review = Review.objects.get(product=product)
        assert review.is_approved is False

    def test_cannot_review_twice(self, authenticated_client, user, product):
        Review.objects.create(
            user=user,
            product=product,
            rating=4,
            title="Primo",
            body="First review.",
        )

        response = authenticated_client.post(
            f"/api/products/{product.slug}/reviews/create/",
            {
                "rating": 5,
                "title": "Secondo",
                "body": "Second review.",
            },
            format="json",
        )
        assert response.status_code == 409

    def test_review_requires_auth(self, api_client, product):
        response = api_client.post(
            f"/api/products/{product.slug}/reviews/create/",
            {
                "rating": 5,
                "title": "Test",
                "body": "Test body.",
            },
            format="json",
        )
        assert response.status_code == 401

    def test_unapproved_reviews_not_in_list(
        self, api_client, authenticated_client, user, product
    ):
        """Only approved reviews appear in the public list."""
        authenticated_client.post(
            f"/api/products/{product.slug}/reviews/create/",
            {
                "rating": 5,
                "title": "Test",
                "body": "Test body.",
            },
            format="json",
        )

        response = api_client.get(
            f"/api/products/{product.slug}/reviews/"
        )
        assert response.status_code == 200
        assert len(response.data["results"]) == 0  # Not yet approved
