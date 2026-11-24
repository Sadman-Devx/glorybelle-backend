import io
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import Group, User
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.catalog.models import (
    Category,
    MediaAsset,
    PendingMediaUpload,
    Product,
    ProductImage,
    ProductVariant,
)
from apps.orders.models import Order, OrderItem


PRODUCTS_URL = "/api/admin/products/"
CATEGORIES_URL = "/api/admin/categories/"
MEDIA_URL = "/api/admin/media/"
MEDIA_PRESIGN_URL = "/api/admin/media/presign/"


@pytest.fixture
def catalogue_users(db):
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    viewer_group, _ = Group.objects.get_or_create(name="Viewer")
    manager = User.objects.create_user(
        username="catalog-manager",
        email="catalog-manager@example.test",
        password="ManagerPass123!",
        is_staff=True,
    )
    manager.groups.add(manager_group)
    viewer = User.objects.create_user(
        username="catalog-viewer",
        email="catalog-viewer@example.test",
        password="ViewerPass123!",
        is_staff=True,
    )
    viewer.groups.add(viewer_group)
    customer = User.objects.create_user(
        username="catalog-customer",
        email="catalog-customer@example.test",
        password="CustomerPass123!",
    )
    superuser = User.objects.create_superuser(
        username="catalog-root",
        email="catalog-root@example.test",
        password="RootPass123!",
    )
    return {
        "manager": manager,
        "viewer": viewer,
        "customer": customer,
        "superuser": superuser,
    }


@pytest.fixture
def catalogue_category(db):
    return Category.objects.create(name="Anelli", slug="anelli")


@pytest.fixture
def admin_client():
    return APIClient()


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _product(category, **overrides):
    values = {
        "category": category,
        "name": "Anello artigianale",
        "slug": "anello-artigianale",
        "description": "Lavorato a mano.",
        "base_price": "120.00",
    }
    values.update(overrides)
    return Product.objects.create(**values)


@pytest.mark.django_db
def test_catalogue_permissions_and_product_crud(
    catalogue_users, catalogue_category, admin_client
):
    assert admin_client.get(PRODUCTS_URL).status_code == 401

    customer_client = _client_for(catalogue_users["customer"])
    assert customer_client.get(PRODUCTS_URL).status_code == 403

    viewer_client = _client_for(catalogue_users["viewer"])
    assert viewer_client.get(PRODUCTS_URL).status_code == 200
    assert viewer_client.post(
        PRODUCTS_URL,
        {"name": "Anello", "category": catalogue_category.pk, "base_price": "10.00"},
        format="json",
    ).status_code == 403

    manager_client = _client_for(catalogue_users["manager"])
    created = manager_client.post(
        PRODUCTS_URL,
        {
            "name": "Anello d'oro",
            "category": catalogue_category.pk,
            "base_price": "149.00",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["slug"] == "anello-doro"
    assert created.data["category"] == catalogue_category.pk
    filtered = manager_client.get(
        PRODUCTS_URL,
        {"category": catalogue_category.pk, "search": "d'oro"},
    )
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.data["results"]] == [created.data["id"]]
    product_url = f"{PRODUCTS_URL}{created.data['id']}/"
    updated = manager_client.patch(
        product_url,
        {"is_active": False, "base_price": "159.00"},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["is_active"] is False
    assert updated.data["base_price"] == "159.00"
    assert Product.history.filter(id=created.data["id"], history_user=catalogue_users["manager"]).exists()
    viewer_variant_write = _client_for(catalogue_users["viewer"]).post(
        f"{PRODUCTS_URL}{created.data['id']}/variants/",
        {
            "metal": "gold",
            "size": "54",
            "sku": "VIEWER-AN-54",
            "stock_quantity": 1,
        },
        format="json",
    )
    assert viewer_variant_write.status_code == 403

    root_client = _client_for(catalogue_users["superuser"])
    assert root_client.post(
        PRODUCTS_URL,
        {
            "name": "Collana",
            "category": catalogue_category.pk,
            "base_price": "99.00",
        },
        format="json",
    ).status_code == 201


@pytest.mark.django_db
def test_admin_categories_are_paginated_and_read_only(
    catalogue_users, catalogue_category
):
    inactive = Category.objects.create(
        name="Collane",
        slug="collane",
        is_active=False,
    )
    assert APIClient().get(CATEGORIES_URL).status_code == 401
    assert (
        _client_for(catalogue_users["customer"]).get(CATEGORIES_URL).status_code
        == 403
    )
    response = _client_for(catalogue_users["viewer"]).get(
        CATEGORIES_URL,
        {"page_size": 1, "ordering": "name"},
    )
    assert response.status_code == 200
    assert response.data["count"] == 2
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["name"] == "Anelli"
    assert _client_for(catalogue_users["manager"]).get(CATEGORIES_URL).status_code == 200
    assert _client_for(catalogue_users["viewer"]).post(
        CATEGORIES_URL,
        {"name": "Orecchini"},
        format="json",
    ).status_code == 403
    assert _client_for(catalogue_users["manager"]).post(
        CATEGORIES_URL,
        {"name": "Orecchini"},
        format="json",
    ).status_code == 405
    assert Category.objects.filter(pk=inactive.pk).exists()


@pytest.mark.django_db
def test_ordered_product_is_deactivated_instead_of_deleted(
    catalogue_users, catalogue_category
):
    product = _product(catalogue_category)
    variant = ProductVariant.objects.create(
        product=product,
        metal="gold",
        size="52",
        sku="ORDERED-AN-52",
        stock_quantity=2,
    )
    order = Order.objects.create(
        order_number="GB-MEDIA-001",
        email="buyer@example.test",
        shipping_first_name="Ada",
        shipping_last_name="Lodi",
        shipping_line1="Via Roma 1",
        shipping_city="Milano",
        shipping_province="MI",
        shipping_postal_code="20100",
        subtotal="120.00",
        total="120.00",
    )
    OrderItem.objects.create(
        order=order,
        variant=variant,
        product_name=product.name,
        variant_metal=variant.metal,
        variant_metal_display="Oro 18K",
        variant_size=variant.size,
        sku=variant.sku,
        unit_price="120.00",
        quantity=1,
        line_total="120.00",
    )

    manager_client = _client_for(catalogue_users["manager"])
    variant_delete = manager_client.delete(
        f"{PRODUCTS_URL}{product.pk}/variants/{variant.pk}/"
    )
    assert variant_delete.status_code == 200
    variant.refresh_from_db()
    assert variant.is_active is False

    response = manager_client.delete(f"{PRODUCTS_URL}{product.pk}/")
    assert response.status_code == 200
    product.refresh_from_db()
    assert product.is_active is False
    assert Product.objects.filter(pk=product.pk).exists()


@pytest.mark.django_db
def test_variant_crud_enforces_unique_sku_and_reserved_stock(
    catalogue_users, catalogue_category
):
    product = _product(catalogue_category)
    url = f"{PRODUCTS_URL}{product.pk}/variants/"
    client = _client_for(catalogue_users["manager"])
    created = client.post(
        url,
        {
            "metal": "gold",
            "size": "52",
            "sku": "AN-52-GOLD",
            "price_override": "99.50",
            "stock_quantity": 3,
        },
        format="json",
    )
    assert created.status_code == 201
    variant_url = f"{url}{created.data['id']}/"
    assert client.patch(
        variant_url,
        {"stock_quantity": 1},
        format="json",
    ).status_code == 200

    ProductVariant.objects.filter(pk=created.data["id"]).update(reserved_quantity=2)
    assert client.patch(
        variant_url,
        {"stock_quantity": 1},
        format="json",
    ).status_code == 400
    duplicate_sku = client.post(
        url,
        {
            "metal": "silver",
            "size": "52",
            "sku": "AN-52-GOLD",
            "stock_quantity": 1,
        },
        format="json",
    )
    assert duplicate_sku.status_code == 400
    duplicate_combination = client.post(
        url,
        {
            "metal": "gold",
            "size": "52",
            "sku": "AN-52-GOLD-SECOND",
            "stock_quantity": 1,
        },
        format="json",
    )
    assert duplicate_combination.status_code == 400


@pytest.fixture
def s3_client_mock(monkeypatch, settings):
    settings.ADMIN_MEDIA_S3_BUCKET = "test-admin-media"
    settings.ADMIN_MEDIA_S3_REGION = "eu-central-1"
    settings.ADMIN_MEDIA_S3_ENDPOINT_URL = "https://s3.example.test"
    settings.ADMIN_MEDIA_PUBLIC_BASE_URL = "https://cdn.example.test"
    settings.ADMIN_MEDIA_PRESIGN_TTL = 300

    client = Mock()
    client.generate_presigned_url.return_value = "https://s3.example.test/signed"
    client.delete_objects.return_value = {"Errors": []}
    monkeypatch.setattr("admin_api.media_views.get_s3_client", lambda: client)
    return client


@pytest.mark.django_db
def test_media_presign_validates_type_and_size(catalogue_users, s3_client_mock):
    client = _client_for(catalogue_users["manager"])
    accepted = client.post(
        MEDIA_PRESIGN_URL,
        {"content_type": "image/webp", "size_bytes": 100},
        format="json",
    )
    assert accepted.status_code == 201
    assert accepted.data["method"] == "PUT"
    assert accepted.data["headers"] == {"Content-Type": "image/webp"}
    assert PendingMediaUpload.objects.filter(
        pk=accepted.data["upload_id"],
        uploaded_by=catalogue_users["manager"],
    ).exists()

    invalid_type = client.post(
        MEDIA_PRESIGN_URL,
        {"content_type": "text/plain", "size_bytes": 100},
        format="json",
    )
    oversized = client.post(
        MEDIA_PRESIGN_URL,
        {"content_type": "image/png", "size_bytes": 10 * 1024 * 1024 + 1},
        format="json",
    )
    assert invalid_type.status_code == 400
    assert oversized.status_code == 400
    assert s3_client_mock.generate_presigned_url.call_count == 1
    presign_params = s3_client_mock.generate_presigned_url.call_args.kwargs["Params"]
    assert presign_params["ContentLength"] == 100
    assert (
        _client_for(catalogue_users["viewer"]).post(
            MEDIA_PRESIGN_URL,
            {"content_type": "image/png", "size_bytes": 100},
            format="json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_media_registration_rejects_disguised_non_image(
    catalogue_users, s3_client_mock
):
    data = b"MZThis is not a PNG image"
    pending = PendingMediaUpload.objects.create(
        object_key="staging/disguised",
        content_type="image/png",
        declared_size_bytes=len(data),
        uploaded_by=catalogue_users["manager"],
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    s3_client_mock.head_object.return_value = {"ContentLength": len(data)}
    s3_client_mock.get_object.return_value = {"Body": io.BytesIO(data)}

    response = _client_for(catalogue_users["manager"]).post(
        MEDIA_URL,
        {"upload_id": pending.pk},
        format="json",
    )
    assert response.status_code == 400
    assert not MediaAsset.objects.exists()
    assert not PendingMediaUpload.objects.filter(pk=pending.pk).exists()


@pytest.mark.django_db
def test_media_registration_rejects_actual_oversized_object(
    catalogue_users, s3_client_mock
):
    pending = PendingMediaUpload.objects.create(
        object_key="staging/oversized",
        content_type="image/jpeg",
        declared_size_bytes=100,
        uploaded_by=catalogue_users["manager"],
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    s3_client_mock.head_object.return_value = {
        "ContentLength": 10 * 1024 * 1024 + 1
    }

    response = _client_for(catalogue_users["manager"]).post(
        MEDIA_URL,
        {"upload_id": pending.pk},
        format="json",
    )
    assert response.status_code == 400
    s3_client_mock.get_object.assert_not_called()
    assert not MediaAsset.objects.exists()


@pytest.mark.django_db
def test_media_registration_reencodes_and_creates_webp_variants(
    catalogue_users, s3_client_mock
):
    source = Image.new("RGB", (900, 600), color="purple")
    exif = Image.Exif()
    exif[0x010E] = "Sensitive source metadata"
    image_bytes = io.BytesIO()
    source.save(image_bytes, format="JPEG", exif=exif)
    data = image_bytes.getvalue()
    pending = PendingMediaUpload.objects.create(
        object_key="staging/valid-image",
        content_type="image/jpeg",
        declared_size_bytes=len(data),
        uploaded_by=catalogue_users["manager"],
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    s3_client_mock.head_object.return_value = {"ContentLength": len(data)}
    s3_client_mock.get_object.return_value = {"Body": io.BytesIO(data)}
    uploaded = {}

    def store_object(**kwargs):
        uploaded[kwargs["Key"]] = kwargs

    s3_client_mock.put_object.side_effect = store_object

    response = _client_for(catalogue_users["manager"]).post(
        MEDIA_URL,
        {"upload_id": pending.pk, "alt_text": "Anello"},
        format="json",
    )
    assert response.status_code == 201
    asset = MediaAsset.objects.get(pk=response.data["id"])
    assert asset.width == 900
    assert asset.height == 600
    assert asset.alt_text == "Anello"
    assert len(uploaded) == 3
    assert {row["ContentType"] for row in uploaded.values()} == {"image/webp"}
    for row in uploaded.values():
        rendition = Image.open(io.BytesIO(row["Body"]))
        assert rendition.format == "WEBP"
        assert not rendition.getexif()
    assert response.data["url_800"].startswith("https://cdn.example.test/")


@pytest.mark.django_db
def test_gallery_order_primary_usage_count_and_delete_conflict(
    catalogue_users, catalogue_category, s3_client_mock
):
    product = _product(catalogue_category)
    first = MediaAsset.objects.create(
        object_key_400="catalog/a/400.webp",
        object_key_800="catalog/a/800.webp",
        object_key_1600="catalog/a/1600.webp",
        original_size_bytes=100,
        width=800,
        height=600,
        alt_text="Anello principale",
        uploaded_by=catalogue_users["manager"],
    )
    second = MediaAsset.objects.create(
        object_key_400="catalog/b/400.webp",
        object_key_800="catalog/b/800.webp",
        object_key_1600="catalog/b/1600.webp",
        original_size_bytes=200,
        width=800,
        height=600,
        alt_text="Dettaglio anello",
        uploaded_by=catalogue_users["manager"],
    )
    client = _client_for(catalogue_users["manager"])
    gallery_url = f"{PRODUCTS_URL}{product.pk}/images/"
    linked = client.put(
        gallery_url,
        {"media_ids": [second.pk, first.pk], "primary_media_id": first.pk},
        format="json",
    )
    assert linked.status_code == 200
    assert [image["media_id"] for image in linked.data] == [second.pk, first.pk]
    assert linked.data[1]["is_primary"] is True
    assert ProductImage.history.filter(
        product=product,
        history_user=catalogue_users["manager"],
    ).exists()

    viewer_client = _client_for(catalogue_users["viewer"])
    assert APIClient().get(MEDIA_URL).status_code == 401
    assert (
        _client_for(catalogue_users["customer"]).get(MEDIA_URL).status_code == 403
    )
    media_list = viewer_client.get(MEDIA_URL, {"usage_count": 1})
    assert media_list.status_code == 200
    assert len(media_list.data["results"]) == 2
    primary_list = viewer_client.get(
        gallery_url,
        {"is_primary": "true", "search": "Anello"},
    )
    assert primary_list.status_code == 200
    assert [image["media_id"] for image in primary_list.data["results"]] == [
        first.pk
    ]
    assert viewer_client.delete(f"{MEDIA_URL}{first.pk}/").status_code == 403
    assert (
        viewer_client.put(
            gallery_url,
            {"media_ids": [], "primary_media_id": None},
            format="json",
        ).status_code
        == 403
    )

    manager_client = _client_for(catalogue_users["manager"])
    blocked = manager_client.delete(f"{MEDIA_URL}{first.pk}/")
    assert blocked.status_code == 409
    assert blocked.data["detail"]
    unlinked = manager_client.put(
        gallery_url,
        {"media_ids": [second.pk], "primary_media_id": second.pk},
        format="json",
    )
    assert unlinked.status_code == 200
    deleted = manager_client.delete(f"{MEDIA_URL}{first.pk}/")
    assert deleted.status_code == 204
    assert not MediaAsset.objects.filter(pk=first.pk).exists()
