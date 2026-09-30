"""
GLORYBELLE — Account Tests.
"""
import pytest
from django.urls import reverse

from apps.accounts.models import Address, CustomerProfile


@pytest.mark.django_db
class TestRegistration:
    def test_register_success(self, api_client):
        url = reverse("register")
        data = {
            "username": "nuovocliente",
            "email": "cliente@glorybelle.it",
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
            "first_name": "Francesca",
            "last_name": "Rossi",
            "phone": "+39 02 1234567",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == 201
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        # Profile should be created
        assert CustomerProfile.objects.filter(
            user__username="nuovocliente"
        ).exists()

    def test_register_password_mismatch(self, api_client):
        url = reverse("register")
        data = {
            "username": "testuser2",
            "email": "test2@glorybelle.it",
            "password": "SecurePass123!",
            "password_confirm": "DifferentPass123!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == 400

    def test_register_duplicate_email(self, api_client, user):
        url = reverse("register")
        data = {
            "username": "newuser",
            "email": "test@glorybelle.it",  # Same as fixture user
            "password": "SecurePass123!",
            "password_confirm": "SecurePass123!",
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == 400


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client, user):
        url = reverse("token_obtain_pair")
        response = api_client.post(
            url,
            {"username": "testuser", "password": "TestPass123!"},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client, user):
        url = reverse("token_obtain_pair")
        response = api_client.post(
            url,
            {"username": "testuser", "password": "wrongpassword"},
            format="json",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestMeEndpoint:
    def test_me_authenticated(self, authenticated_client, user):
        # Ensure profile exists
        CustomerProfile.objects.get_or_create(user=user)
        url = reverse("me")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert response.data["username"] == "testuser"

    def test_me_unauthenticated(self, api_client):
        url = reverse("me")
        response = api_client.get(url)
        assert response.status_code == 401


@pytest.mark.django_db
class TestAddresses:
    def test_create_address(self, authenticated_client):
        url = reverse("address-list")
        data = {
            "first_name": "Francesca",
            "last_name": "Rossi",
            "line1": "Via Roma 42",
            "city": "Milano",
            "province": "MI",
            "postal_code": "20121",
            "is_default": True,
        }
        response = authenticated_client.post(url, data, format="json")
        assert response.status_code == 201
        assert response.data["city"] == "Milano"

    def test_list_own_addresses(self, authenticated_client, user):
        Address.objects.create(
            user=user,
            first_name="Test",
            last_name="User",
            line1="Via Test 1",
            city="Roma",
            province="RM",
            postal_code="00100",
        )
        url = reverse("address-list")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_cannot_see_other_user_address(self, authenticated_client, admin_user):
        Address.objects.create(
            user=admin_user,
            first_name="Admin",
            last_name="User",
            line1="Via Admin 1",
            city="Torino",
            province="TO",
            postal_code="10100",
        )
        url = reverse("address-list")
        response = authenticated_client.get(url)
        assert len(response.data["results"]) == 0
