import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.enquiries.models import Enquiry, EnquiryNote


PUBLIC_URL = "/api/enquiries/"
ADMIN_URL = "/api/admin/enquiries/"
VALID_ENQUIRY = {
    "name": "Giulia Bianchi",
    "email": "giulia@example.test",
    "topic": "atelier",
    "atelier_type": "anelli",
    "message": "Vorrei informazioni su un anello.",
}


@pytest.fixture(autouse=True)
def clear_enquiry_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def email_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.ENQUIRY_NOTIFICATION_EMAIL = "ordini@glorybelle.it"


@pytest.fixture
def enquiry_admins(db):
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    viewer_group, _ = Group.objects.get_or_create(name="Viewer")

    manager = User.objects.create_user(
        username="enquiry-manager",
        email="manager@example.test",
        is_staff=True,
    )
    manager.groups.add(manager_group)
    viewer = User.objects.create_user(
        username="enquiry-viewer",
        email="viewer@example.test",
        is_staff=True,
    )
    viewer.groups.add(viewer_group)
    second_manager = User.objects.create_user(
        username="enquiry-manager-two",
        email="manager-two@example.test",
        is_staff=True,
    )
    second_manager.groups.add(manager_group)
    customer = User.objects.create_user(
        username="enquiry-customer",
        email="customer@example.test",
    )
    superuser = User.objects.create_superuser(
        username="enquiry-root",
        email="root@example.test",
        password="TestPass123!",
    )
    return {
        "manager": manager,
        "manager_two": second_manager,
        "viewer": viewer,
        "customer": customer,
        "superuser": superuser,
    }


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_public_enquiry_is_saved_as_plain_text_and_emails_shop(email_settings):
    response = APIClient().post(
        PUBLIC_URL,
        {**VALID_ENQUIRY, "message": "Ciao <strong>GLORYBELLE</strong>!"},
        format="json",
    )

    assert response.status_code == 201
    enquiry = Enquiry.objects.get()
    assert enquiry.name == VALID_ENQUIRY["name"]
    assert enquiry.atelier_type == "anelli"
    assert enquiry.message == "Ciao GLORYBELLE!"
    assert enquiry.status == "new"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["ordini@glorybelle.it"]
    assert mail.outbox[0].reply_to == [VALID_ENQUIRY["email"]]
    assert "Nuova richiesta" in mail.outbox[0].subject
    assert "È arrivata una nuova richiesta" in mail.outbox[0].body
    assert mail.outbox[0].alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_honeypot_returns_generic_success_without_storing_or_emailing(email_settings):
    response = APIClient().post(
        PUBLIC_URL,
        {**VALID_ENQUIRY, "website": "https://spam.example.test"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data == {
        "message": (
            "Grazie per aver contattato GLORYBELLE. "
            "La richiesta è stata ricevuta."
        )
    }
    assert not Enquiry.objects.exists()
    assert not mail.outbox


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"topic": "supporto"}, "topic"),
        ({"atelier_type": "bracciali"}, "atelier_type"),
        ({"topic": "ordine", "atelier_type": "anelli"}, "atelier_type"),
        ({"message": "<b></b>"}, "message"),
        ({"message": "x" * 5001}, "message"),
    ],
)
def test_public_enquiry_rejects_invalid_fields(changes, field, email_settings):
    response = APIClient().post(
        PUBLIC_URL,
        {**VALID_ENQUIRY, **changes},
        format="json",
    )

    assert response.status_code == 400
    assert field in response.data
    assert not Enquiry.objects.exists()
    assert not mail.outbox


@pytest.mark.django_db
def test_public_enquiry_is_limited_to_five_requests_per_ip(email_settings):
    client = APIClient()
    for _ in range(5):
        response = client.post(
            PUBLIC_URL,
            VALID_ENQUIRY,
            format="json",
            REMOTE_ADDR="198.51.100.24",
        )
        assert response.status_code == 201

    limited = client.post(
        PUBLIC_URL,
        VALID_ENQUIRY,
        format="json",
        REMOTE_ADDR="198.51.100.24",
    )
    assert limited.status_code == 429
    assert Enquiry.objects.count() == 5
    assert len(mail.outbox) == 5

    other_ip = client.post(
        PUBLIC_URL,
        VALID_ENQUIRY,
        format="json",
        REMOTE_ADDR="198.51.100.25",
    )
    assert other_ip.status_code == 201
    assert Enquiry.objects.count() == 6
    assert len(mail.outbox) == 6


@pytest.mark.django_db
def test_admin_enquiry_read_permissions_and_paginated_search(enquiry_admins):
    first = Enquiry.objects.create(**VALID_ENQUIRY)
    Enquiry.objects.create(
        name="Marco Rossi",
        email="marco@example.test",
        topic="ordine",
        message="Informazioni sull'ordine.",
    )

    assert APIClient().get(ADMIN_URL).status_code == 401
    assert _client_for(enquiry_admins["customer"]).get(ADMIN_URL).status_code == 403
    assert APIClient().get(f"{ADMIN_URL}{first.pk}/").status_code == 401
    assert (
        _client_for(enquiry_admins["customer"])
        .get(f"{ADMIN_URL}{first.pk}/")
        .status_code
        == 403
    )

    viewer = _client_for(enquiry_admins["viewer"])
    response = viewer.get(
        ADMIN_URL,
        {"search": "Giulia", "status": "new", "page_size": 1},
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == first.pk
    detail = viewer.get(f"{ADMIN_URL}{first.pk}/")
    assert detail.status_code == 200
    assert detail.data["message"] == VALID_ENQUIRY["message"]
    assert detail.data["internal_notes"] == []

    assert _client_for(enquiry_admins["manager"]).get(ADMIN_URL).status_code == 200
    assert _client_for(enquiry_admins["superuser"]).get(ADMIN_URL).status_code == 200
    assert (
        _client_for(enquiry_admins["manager"])
        .get(f"{ADMIN_URL}{first.pk}/")
        .status_code
        == 200
    )
    assert (
        _client_for(enquiry_admins["superuser"])
        .get(f"{ADMIN_URL}{first.pk}/")
        .status_code
        == 200
    )


@pytest.mark.django_db
def test_admin_enquiry_assignees_are_searchable_and_role_protected(enquiry_admins):
    url = f"{ADMIN_URL}assignees/"
    assert APIClient().get(url).status_code == 401
    assert _client_for(enquiry_admins["customer"]).get(url).status_code == 403

    response = _client_for(enquiry_admins["viewer"]).get(
        url,
        {"search": "manager-two", "page_size": 1},
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0] == {
        "id": enquiry_admins["manager_two"].pk,
        "name": "enquiry-manager-two",
        "email": "manager-two@example.test",
    }
    assert _client_for(enquiry_admins["manager"]).get(url).status_code == 200
    assert _client_for(enquiry_admins["superuser"]).get(url).status_code == 200


@pytest.mark.django_db
def test_admin_manager_can_assign_change_status_and_add_private_notes(enquiry_admins):
    enquiry = Enquiry.objects.create(**VALID_ENQUIRY)
    manager = _client_for(enquiry_admins["manager"])
    patch_response = manager.patch(
        f"{ADMIN_URL}{enquiry.pk}/",
        {
            "status": "answered",
            "assigned_to": enquiry_admins["manager_two"].pk,
        },
        format="json",
    )
    assert patch_response.status_code == 200
    assert patch_response.data["internal_notes"] == []
    enquiry.refresh_from_db()
    assert enquiry.status == "answered"
    assert enquiry.assigned_to == enquiry_admins["manager_two"]

    invalid_assignment = manager.patch(
        f"{ADMIN_URL}{enquiry.pk}/",
        {"assigned_to": enquiry_admins["viewer"].pk},
        format="json",
    )
    assert invalid_assignment.status_code == 400

    note_response = manager.post(
        f"{ADMIN_URL}{enquiry.pk}/notes/",
        {"body": "Verificare la disponibilità in atelier."},
        format="json",
    )
    assert note_response.status_code == 201
    assert note_response.data["author_id"] == enquiry_admins["manager"].pk
    assert EnquiryNote.objects.filter(
        enquiry=enquiry,
        author=enquiry_admins["manager"],
    ).exists()

    detail = _client_for(enquiry_admins["viewer"]).get(f"{ADMIN_URL}{enquiry.pk}/")
    assert detail.data["status"] == "answered"
    assert detail.data["internal_notes"][0]["body"] == note_response.data["body"]


@pytest.mark.django_db
def test_viewer_cannot_update_or_add_notes_and_customer_cannot_read(enquiry_admins):
    enquiry = Enquiry.objects.create(**VALID_ENQUIRY)
    notes_url = f"{ADMIN_URL}{enquiry.pk}/notes/"
    payload = {"body": "Nota privata"}

    assert _client_for(enquiry_admins["viewer"]).patch(
        f"{ADMIN_URL}{enquiry.pk}/",
        {"status": "closed"},
        format="json",
    ).status_code == 403
    assert _client_for(enquiry_admins["viewer"]).post(
        notes_url,
        payload,
        format="json",
    ).status_code == 403
    assert _client_for(enquiry_admins["customer"]).get(
        f"{ADMIN_URL}{enquiry.pk}/"
    ).status_code == 403
    assert APIClient().post(notes_url, payload, format="json").status_code == 401


@pytest.mark.django_db
def test_admin_enquiry_write_routes_enforce_role_matrix(enquiry_admins):
    enquiry = Enquiry.objects.create(**VALID_ENQUIRY)
    routes = (
        (
            "patch",
            f"{ADMIN_URL}{enquiry.pk}/",
            {"status": "in_progress"},
            200,
        ),
        (
            "post",
            f"{ADMIN_URL}{enquiry.pk}/notes/",
            {"body": "Nota interna"},
            201,
        ),
    )

    for method, url, payload, success_status in routes:
        anonymous_response = getattr(APIClient(), method)(
            url,
            payload,
            format="json",
        )
        customer_response = getattr(_client_for(enquiry_admins["customer"]), method)(
            url,
            payload,
            format="json",
        )
        viewer_response = getattr(_client_for(enquiry_admins["viewer"]), method)(
            url,
            payload,
            format="json",
        )
        manager_response = getattr(_client_for(enquiry_admins["manager"]), method)(
            url,
            payload,
            format="json",
        )
        superuser_response = getattr(_client_for(enquiry_admins["superuser"]), method)(
            url,
            payload,
            format="json",
        )

        assert anonymous_response.status_code == 401
        assert customer_response.status_code == 403
        assert viewer_response.status_code == 403
        assert manager_response.status_code == success_status
        assert superuser_response.status_code == success_status
