import re
import uuid

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from rest_framework.test import APIClient

from admin_api.models import StaffRoleChange
from apps.catalog.models import MediaAsset
from apps.site_content.models import (
    HeroImage,
    InstagramGridImage,
    Testimonial as SiteTestimonial,
)


CONTENT_HERO_URL = "/api/admin/content/hero/"
CONTENT_INSTAGRAM_URL = "/api/admin/content/instagram/"
CONTENT_TESTIMONIALS_URL = "/api/admin/content/testimonials/"
STAFF_URL = "/api/admin/staff/"


@pytest.fixture
def staff_users(db):
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    viewer_group, _ = Group.objects.get_or_create(name="Viewer")
    manager = User.objects.create_user(
        username="content-manager",
        email="content-manager@example.test",
        is_staff=True,
    )
    manager.groups.add(manager_group)
    viewer = User.objects.create_user(
        username="content-viewer",
        email="content-viewer@example.test",
        is_staff=True,
    )
    viewer.groups.add(viewer_group)
    customer = User.objects.create_user(
        username="content-customer",
        email="content-customer@example.test",
    )
    superuser = User.objects.create_superuser(
        username="content-root",
        email="content-root@example.test",
        password="RootPass123!",
    )
    return {
        "manager": manager,
        "viewer": viewer,
        "customer": customer,
        "superuser": superuser,
    }


@pytest.fixture
def media_assets(db, settings):
    settings.ADMIN_MEDIA_PUBLIC_BASE_URL = "https://cdn.example.test"
    assets = []
    for index in range(7):
        key = f"site-content/{uuid.uuid4().hex}"
        assets.append(
            MediaAsset.objects.create(
                object_key_400=f"{key}-400.webp",
                object_key_800=f"{key}-800.webp",
                object_key_1600=f"{key}-1600.webp",
                original_size_bytes=1000,
                width=800,
                height=800,
                alt_text=f"Gioiello {index + 1}",
            )
        )
    return assets


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_public_content_falls_back_when_no_managed_content_exists():
    client = APIClient()
    hero = client.get("/api/site-content/hero/")
    instagram = client.get("/api/site-content/instagram/")
    testimonials = client.get("/api/site-content/testimonials/")

    assert hero.status_code == 200
    assert hero.data["count"] == 0
    assert instagram.status_code == 200
    assert instagram.data == {"link": "", "images": []}
    assert testimonials.status_code == 200
    assert testimonials.data["count"] == 0


@pytest.mark.django_db
def test_hero_admin_permissions_crud_search_order_and_public_output(
    staff_users, media_assets
):
    anonymous = APIClient()
    assert anonymous.get(CONTENT_HERO_URL).status_code == 401
    assert anonymous.post(
        CONTENT_HERO_URL,
        {"media_asset_id": media_assets[0].pk},
        format="json",
    ).status_code == 401

    customer = _client_for(staff_users["customer"])
    assert customer.get(CONTENT_HERO_URL).status_code == 403

    viewer = _client_for(staff_users["viewer"])
    assert viewer.get(CONTENT_HERO_URL).status_code == 200
    assert viewer.post(
        CONTENT_HERO_URL,
        {"media_asset_id": media_assets[0].pk},
        format="json",
    ).status_code == 403

    manager = _client_for(staff_users["manager"])
    first = manager.post(
        CONTENT_HERO_URL,
        {"media_asset_id": media_assets[0].pk, "sort_order": 5},
        format="json",
    )
    second = manager.post(
        CONTENT_HERO_URL,
        {"media_asset_id": media_assets[1].pk, "sort_order": 10},
        format="json",
    )
    assert first.status_code == second.status_code == 201
    assert first.data["media"]["url_800"].endswith(media_assets[0].object_key_800)

    results = manager.get(CONTENT_HERO_URL, {"search": "Gioiello 2", "page_size": 1})
    assert results.status_code == 200
    assert results.data["count"] == 1
    assert [row["id"] for row in results.data["results"]] == [second.data["id"]]

    reordered = manager.patch(
        f"{CONTENT_HERO_URL}{first.data['id']}/",
        {"sort_order": 20},
        format="json",
    )
    assert reordered.status_code == 200
    assert list(
        HeroImage.objects.values_list("sort_order", flat=True).order_by("sort_order")
    ) == [10, 20]

    public = APIClient().get("/api/site-content/hero/")
    assert public.status_code == 200
    assert [row["id"] for row in public.data["results"]] == [
        second.data["id"],
        first.data["id"],
    ]
    assert public.data["results"][0]["image_url"].endswith(
        media_assets[1].object_key_1600
    )

    removed = manager.delete(f"{CONTENT_HERO_URL}{first.data['id']}/")
    assert removed.status_code == 204
    assert not HeroImage.objects.filter(pk=first.data["id"]).exists()


@pytest.mark.django_db
def test_instagram_grid_requires_unique_assets_and_only_publishes_seven(
    staff_users, media_assets
):
    assert APIClient().get(CONTENT_INSTAGRAM_URL).status_code == 401
    assert _client_for(staff_users["customer"]).get(CONTENT_INSTAGRAM_URL).status_code == 403
    assert _client_for(staff_users["viewer"]).get(CONTENT_INSTAGRAM_URL).status_code == 200
    assert _client_for(staff_users["viewer"]).put(
        CONTENT_INSTAGRAM_URL,
        {"link": "https://instagram.com/glorybelle", "image_asset_ids": [1] * 7},
        format="json",
    ).status_code == 403

    manager = _client_for(staff_users["manager"])
    assert manager.put(
        CONTENT_INSTAGRAM_URL,
        {
            "link": "https://instagram.com/glorybelle",
            "image_asset_ids": [asset.pk for asset in media_assets[:6]],
        },
        format="json",
    ).status_code == 400
    assert manager.put(
        CONTENT_INSTAGRAM_URL,
        {
            "link": "https://instagram.com/glorybelle",
            "image_asset_ids": [media_assets[0].pk] * 7,
        },
        format="json",
    ).status_code == 400

    partial = manager.put(
        CONTENT_INSTAGRAM_URL,
        {
            "link": "https://instagram.com/glorybelle",
            "image_asset_ids": [media_assets[0].pk, None, None, None, None, None, None],
        },
        format="json",
    )
    assert partial.status_code == 200
    assert APIClient().get("/api/site-content/instagram/").data == {
        "link": "",
        "images": [],
    }

    saved = manager.put(
        CONTENT_INSTAGRAM_URL,
        {
            "link": "https://instagram.com/glorybelle",
            "image_asset_ids": [asset.pk for asset in media_assets],
        },
        format="json",
    )
    assert saved.status_code == 200
    assert len(saved.data["images"]) == 7
    public = APIClient().get("/api/site-content/instagram/")
    assert public.status_code == 200
    assert public.data["link"] == "https://instagram.com/glorybelle"
    assert len(public.data["images"]) == 7
    assert InstagramGridImage.objects.count() == 7


@pytest.mark.django_db
def test_testimonials_admin_filter_and_public_active_only(staff_users, media_assets):
    assert APIClient().get(CONTENT_TESTIMONIALS_URL).status_code == 401
    assert _client_for(staff_users["customer"]).get(CONTENT_TESTIMONIALS_URL).status_code == 403
    assert _client_for(staff_users["viewer"]).get(CONTENT_TESTIMONIALS_URL).status_code == 200
    assert _client_for(staff_users["viewer"]).post(
        CONTENT_TESTIMONIALS_URL,
        {
            "name": "Ada",
            "quote": "Bellissimo.",
            "photo_asset_id": media_assets[0].pk,
        },
        format="json",
    ).status_code == 403

    manager = _client_for(staff_users["manager"])
    active = manager.post(
        CONTENT_TESTIMONIALS_URL,
        {
            "name": "Giulia",
            "quote": "Un gioiello meraviglioso.",
            "photo_asset_id": media_assets[0].pk,
            "active": True,
        },
        format="json",
    )
    inactive = manager.post(
        CONTENT_TESTIMONIALS_URL,
        {
            "name": "Marta",
            "quote": "Una bella esperienza.",
            "photo_asset_id": media_assets[1].pk,
            "active": False,
        },
        format="json",
    )
    assert active.status_code == inactive.status_code == 201
    filtered = manager.get(CONTENT_TESTIMONIALS_URL, {"search": "Giulia", "active": "true"})
    assert filtered.status_code == 200
    assert filtered.data["count"] == 1
    assert filtered.data["results"][0]["id"] == active.data["id"]

    public = APIClient().get("/api/site-content/testimonials/")
    assert public.status_code == 200
    assert public.data["count"] == 1
    assert public.data["results"][0]["name"] == "Giulia"
    assert public.data["results"][0]["photo_url"].endswith(
        media_assets[0].object_key_400
    )
    updated = manager.patch(
        f"{CONTENT_TESTIMONIALS_URL}{active.data['id']}/",
        {"active": False},
        format="json",
    )
    assert updated.status_code == 200
    assert APIClient().get("/api/site-content/testimonials/").data["count"] == 0
    assert manager.delete(f"{CONTENT_TESTIMONIALS_URL}{inactive.data['id']}/").status_code == 204
    assert not SiteTestimonial.objects.filter(pk=inactive.data["id"]).exists()


@pytest.mark.django_db
def test_content_media_assets_are_counted_and_cannot_be_deleted(
    staff_users, media_assets, monkeypatch
):
    HeroImage.objects.create(media_asset=media_assets[0])
    HeroImage.objects.create(media_asset=media_assets[0])
    SiteTestimonial.objects.create(
        name="Cliente",
        quote="Ottimo.",
        photo_asset=media_assets[0],
    )
    manager = _client_for(staff_users["manager"])
    listing = manager.get("/api/admin/media/", {"search": "Gioiello 1"})
    asset = next(row for row in listing.data["results"] if row["id"] == media_assets[0].pk)
    assert asset["usage_count"] == 3

    def unexpected_storage_call():
        raise AssertionError("Il file usato dal contenuto non deve essere eliminato.")

    monkeypatch.setattr("admin_api.media_views.get_s3_client", unexpected_storage_call)
    response = manager.delete(f"/api/admin/media/{media_assets[0].pk}/")
    assert response.status_code == 409
    assert MediaAsset.objects.filter(pk=media_assets[0].pk).exists()


@pytest.mark.django_db
def test_django_user_admin_records_role_changes(staff_users, monkeypatch):
    from apps.accounts.admin import UserAdmin

    target = User.objects.create_user(
        username="admin-role-target",
        email="admin-role-target@example.test",
        is_staff=True,
    )
    target.groups.add(Group.objects.get(name="Viewer"))
    request = type("Request", (), {"user": staff_users["superuser"]})()
    form = type("Form", (), {"instance": target})()
    monkeypatch.setattr(BaseUserAdmin, "save_related", lambda *args, **kwargs: None)

    model_admin = UserAdmin(User, admin.site)
    model_admin.save_model(request, target, form, change=True)
    target.groups.clear()
    target.groups.add(Group.objects.get(name="Manager"))
    model_admin.save_related(request, form, [], change=True)

    audit = StaffRoleChange.objects.get(target_user=target)
    assert (audit.from_role, audit.to_role) == ("viewer", "manager")


@pytest.mark.django_db
def test_staff_invite_role_audit_and_password_setup_link(
    staff_users, settings
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_URL = "https://shop.example.test"
    client = APIClient()
    payload = {
        "email": "new.manager@example.test",
        "first_name": "Ada",
        "last_name": "Rossi",
        "role": "manager",
    }
    assert client.get(STAFF_URL).status_code == 401
    assert client.post(STAFF_URL, payload, format="json").status_code == 401
    assert _client_for(staff_users["customer"]).get(STAFF_URL).status_code == 403
    assert _client_for(staff_users["manager"]).get(STAFF_URL).status_code == 403

    root = _client_for(staff_users["superuser"])
    created = root.post(STAFF_URL, payload, format="json")
    assert created.status_code == 201
    assert set(created.data) == {
        "id",
        "email",
        "name",
        "role",
        "is_active",
        "is_superuser",
        "date_joined",
    }
    assert "password" not in created.data
    assert "password_hash" not in created.data
    user = User.objects.get(email=payload["email"])
    assert user.has_usable_password() is False
    assert user.groups.filter(name="Manager").exists()
    assert len(mail.outbox) == 1
    assert "Imposta la tua password" in mail.outbox[0].subject
    match = re.search(
        r"/reset-password\?uid=([^&\s]+)&token=([^\s]+)",
        mail.outbox[0].body,
    )
    assert match
    assert mail.outbox[0].to == [payload["email"]]
    audit = StaffRoleChange.objects.get(target_user=user)
    assert audit.from_role == ""
    assert audit.to_role == "manager"
    assert audit.changed_by == staff_users["superuser"]

    password_response = client.post(
        "/api/accounts/password/reset/confirm/",
        {
            "uid": match.group(1),
            "token": match.group(2),
            "new_password": "NewManagerPass456!",
            "new_password_confirm": "NewManagerPass456!",
        },
        format="json",
    )
    assert password_response.status_code == 200
    user.refresh_from_db()
    assert user.check_password("NewManagerPass456!")

    assert root.post(STAFF_URL, payload, format="json").status_code == 400
    assert root.get(f"{STAFF_URL}role-audit/").data["count"] == 1


@pytest.mark.django_db
def test_staff_role_change_deactivation_and_password_link_permissions(
    staff_users, settings
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    viewer_group = Group.objects.get(name="Viewer")
    target = User.objects.create_user(
        username="role-target",
        email="role-target@example.test",
        is_staff=True,
    )
    target.groups.add(viewer_group)
    root = _client_for(staff_users["superuser"])
    manager = _client_for(staff_users["manager"])
    role_url = f"{STAFF_URL}{target.pk}/"
    assert APIClient().patch(role_url, {"role": "manager"}, format="json").status_code == 401
    assert manager.patch(role_url, {"role": "manager"}, format="json").status_code == 403
    changed = root.patch(role_url, {"role": "manager"}, format="json")
    assert changed.status_code == 200
    assert changed.data["role"] == "manager"
    audit = StaffRoleChange.objects.get(target_user=target)
    assert (audit.from_role, audit.to_role) == ("viewer", "manager")

    self_deactivate = root.post(
        f"{STAFF_URL}{staff_users['superuser'].pk}/deactivate/"
    )
    assert self_deactivate.status_code == 400
    another_superuser = User.objects.create_superuser(
        username="second-root",
        email="second-root@example.test",
        password="RootPass456!",
    )
    assert root.post(
        f"{STAFF_URL}{another_superuser.pk}/deactivate/"
    ).status_code == 400
    deactivated = root.post(f"{STAFF_URL}{target.pk}/deactivate/")
    assert deactivated.status_code == 200
    assert deactivated.data["is_active"] is False
    assert root.post(f"{STAFF_URL}{target.pk}/password-link/").status_code == 400

    link_url = f"{STAFF_URL}{staff_users['manager'].pk}/password-link/"
    assert manager.post(link_url).status_code == 403
    assert root.post(link_url).status_code == 202
    assert mail.outbox[-1].to == [staff_users["manager"].email]
    assert StaffRoleChange.objects.filter(target_user=target).count() == 1

    superuser_role = root.patch(
        f"{STAFF_URL}{staff_users['superuser'].pk}/",
        {"role": "manager"},
        format="json",
    )
    assert superuser_role.status_code == 400
