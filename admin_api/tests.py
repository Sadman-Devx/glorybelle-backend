import time
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from simple_history.utils import update_change_reason

from .permissions import (
    IsAdminRole,
    IsManager,
    IsSuperuser,
    MANAGER_GROUP,
)
from .views import AdminLoginView, AdminMfaVerifyView, AdminTokenRefreshView


ADMIN_ME_URL = "/api/admin/me/"
ADMIN_LOGIN_URL = "/api/admin/login/"
ADMIN_REFRESH_URL = "/api/admin/token/refresh/"
ADMIN_AUDIT_URL = "/api/admin/audit/"
ADMIN_MFA_VERIFY_URL = "/api/admin/mfa/verify/"
ROLE_PERMISSIONS = (IsAdminRole, IsManager, IsSuperuser)


@pytest.fixture(autouse=True)
def isolate_admin_test_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_roles_migration_creates_admin_groups():
    assert Group.objects.filter(name="Manager").exists()
    assert Group.objects.filter(name="Viewer").exists()


def test_cors_uses_an_exact_origin_allowlist():
    assert settings.CORS_ALLOW_ALL_ORIGINS is False
    assert settings.CORS_ALLOWED_ORIGINS
    assert all("*" not in origin for origin in settings.CORS_ALLOWED_ORIGINS)


@pytest.mark.django_db
def test_django_admin_requires_verified_otp_and_sets_security_headers(users):
    device = TOTPDevice.objects.create(
        user=users["superuser"],
        name="admin-totp",
        confirmed=True,
    )
    client = Client()
    client.force_login(users["superuser"])

    unverified = client.get("/admin/")
    assert unverified.status_code == 302
    assert unverified["Location"].startswith("/admin/login/")

    client.force_login(users["superuser"])
    session = client.session
    session["otp_device_id"] = device.persistent_id
    from .models import AdminAuthSession

    admin_session = AdminAuthSession.objects.create(user=users["superuser"])
    session["admin_auth_session_id"] = str(admin_session.session_id)
    session.save()
    verified = client.get("/admin/")
    assert verified.status_code == 200
    assert "frame-ancestors 'none'" in verified["Content-Security-Policy"]
    assert verified["X-Content-Type-Options"] == "nosniff"

    api_response = client.get(ADMIN_ME_URL)
    assert api_response.status_code == 401
    assert "frame-ancestors 'none'" in api_response["Content-Security-Policy"]
    assert api_response["X-Content-Type-Options"] == "nosniff"


@pytest.fixture
def users(db):
    manager_group, _ = Group.objects.get_or_create(name="Manager")
    viewer_group, _ = Group.objects.get_or_create(name="Viewer")

    manager = User.objects.create_user(
        username="manager",
        email="manager@glorybelle.it",
        password="ManagerPass123!",
        is_staff=True,
        first_name="Marta",
        last_name="Rossi",
    )
    manager.groups.add(manager_group)
    viewer = User.objects.create_user(
        username="viewer",
        email="viewer@glorybelle.it",
        password="ViewerPass123!",
        is_staff=True,
    )
    viewer.groups.add(viewer_group)
    superuser = User.objects.create_superuser(
        username="root",
        email="root@glorybelle.it",
        password="RootPass123!",
    )
    customer = User.objects.create_user(
        username="customer",
        email="customer@glorybelle.it",
        password="CustomerPass123!",
    )
    return {
        "manager": manager,
        "viewer": viewer,
        "superuser": superuser,
        "customer": customer,
    }


def test_admin_routes_declare_role_permissions_or_explicit_token_auth():
    from . import urls

    for pattern in urls.urlpatterns:
        view_class = getattr(pattern.callback, "cls", None)
        assert view_class is not None, f"{pattern} is not a class-based view"
        if view_class in (
            AdminLoginView,
            AdminMfaVerifyView,
            AdminTokenRefreshView,
        ):
            assert view_class.permission_classes == [AllowAny]
            continue
        assert any(
            issubclass(permission, ROLE_PERMISSIONS)
            for permission in view_class.permission_classes
        ), f"{pattern} lacks an admin role permission"


@pytest.mark.django_db
def test_admin_url_status_matrix_covers_every_declared_route(users):
    import re

    from django.urls import URLPattern
    from rest_framework_simplejwt.tokens import AccessToken

    from . import urls
    from .models import AdminAuthSession
    from .serializers import AdminRefreshToken

    anonymous = APIClient()
    customer = APIClient()
    customer.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(users['customer'])}"
    )
    staff_clients = {}
    for role in ("viewer", "manager", "superuser"):
        user = users[role]
        TOTPDevice.objects.create(
            user=user,
            name="admin-totp",
            confirmed=True,
        )
        auth_session = AdminAuthSession.objects.create(user=user)
        token = AdminRefreshToken.for_user(user, auth_session.session_id).access_token
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        staff_clients[role] = client

    expected_staff_statuses = {}
    successful_get_routes = {
        "me",
        "audit",
        "content-hero",
        "content-instagram",
        "content-testimonials",
        "staff",
        "staff-role-audit",
        "enquiries",
        "enquiry-assignees",
        "dashboard",
        "admin-categories",
        "orders",
        "media-list-register",
        "admin-products-list",
    }
    routes = [pattern for pattern in urls.urlpatterns if isinstance(pattern, URLPattern)]
    assert routes
    for route_index, pattern in enumerate(routes, start=1):
        view_class = getattr(pattern.callback, "cls", None)
        assert view_class is not None, f"{pattern} is not a class-based view"
        route = str(pattern.pattern)
        route = route.removeprefix("^").removesuffix("$")
        route = re.sub(r"\(\?P<[^>]+>[^)]+\)", "1", route)
        route = re.sub(r"<int:[^>]+>", "1", route)
        route = re.sub(r"<(?:str|slug):[^>]+>", "sample", route)
        url = f"/api/admin/{route}"
        if pattern.name == "audit":
            url += "?model=order"

        view_permissions = view_class.permission_classes
        if view_permissions == [AllowAny]:
            expected = 405
            for client_index, (label, client) in enumerate((
                ("anonymous", anonymous),
                ("customer", customer),
                *staff_clients.items(),
            ), start=1):
                response = client.get(
                    url,
                    REMOTE_ADDR=f"192.0.{route_index}.{client_index}",
                )
                assert response.status_code == expected, (
                    pattern.name,
                    label,
                    response.status_code,
                )
            continue

        assert anonymous.get(
            url, REMOTE_ADDR=f"192.0.{route_index}.1"
        ).status_code == 401, pattern.name
        assert customer.get(
            url, REMOTE_ADDR=f"192.0.{route_index}.2"
        ).status_code == 403, pattern.name
        get_allowed = (
            "get" in getattr(pattern.callback, "actions", {})
            or callable(getattr(view_class, "get", None))
        )
        authorized_statuses = {200, 400, 404} if get_allowed else {405}
        for client_index, (role, client) in enumerate(staff_clients.items(), start=3):
            allowed = all(
                permission().has_permission(
                    SimpleNamespace(user=users[role], method="GET"),
                    None,
                )
                for permission in view_permissions
            )
            response = client.get(
                url,
                REMOTE_ADDR=f"192.0.{route_index}.{client_index}",
            )
            if allowed:
                if get_allowed and pattern.name in successful_get_routes:
                    assert response.status_code == 200, (
                        pattern.name,
                        role,
                        response.status_code,
                    )
                else:
                    assert response.status_code in authorized_statuses, (
                        pattern.name,
                        role,
                        response.status_code,
                    )
            else:
                assert response.status_code == 403, (
                    pattern.name,
                    role,
                    response.status_code,
                )
            expected_staff_statuses.setdefault(pattern.name, {})[role] = (
                response.status_code
            )

    assert len(expected_staff_statuses) == len(
        [pattern for pattern in routes if pattern.callback.cls.permission_classes != [AllowAny]]
    )


@pytest.mark.django_db
def test_me_requires_admin_role_and_returns_role_data(users):
    client = APIClient()
    assert client.get(ADMIN_ME_URL).status_code == 401

    client.force_authenticate(user=users["customer"])
    assert client.get(ADMIN_ME_URL).status_code == 403

    client.force_authenticate(user=users["viewer"])
    response = client.get(ADMIN_ME_URL)
    assert response.status_code == 200
    assert response.data == {
        "id": users["viewer"].id,
        "email": "viewer@glorybelle.it",
        "name": "viewer",
        "role": "viewer",
        "permissions": [
            "orders:read",
            "products:read",
            "media:read",
            "enquiries:read",
            "content:read",
        ],
    }

    client.force_authenticate(user=users["manager"])
    assert client.get(ADMIN_ME_URL).data["role"] == "manager"


@pytest.mark.django_db
def test_manager_permission_requires_staff_group(users):
    permission = IsManager()

    assert permission.has_permission(SimpleNamespace(user=users["manager"]), None)
    assert permission.has_permission(SimpleNamespace(user=users["superuser"]), None)
    assert not permission.has_permission(SimpleNamespace(user=users["viewer"]), None)
    assert not permission.has_permission(SimpleNamespace(user=users["customer"]), None)

    non_staff = User.objects.create_user(username="nonstaff", password="Pass123!")
    non_staff.groups.add(Group.objects.get(name=MANAGER_GROUP))
    assert not IsAdminRole().has_permission(SimpleNamespace(user=non_staff), None)


@pytest.mark.django_db
def test_login_is_staff_only_and_uses_same_generic_error(users):
    client = APIClient()
    enrollment = client.post(
        ADMIN_LOGIN_URL,
        {"email": "manager@glorybelle.it", "password": "ManagerPass123!"},
        format="json",
    )
    assert enrollment.status_code == 200
    assert enrollment.data["mfa_required"] is True
    assert enrollment.data["purpose"] == "enroll"
    assert "secret" in enrollment.data
    assert "access" not in enrollment.data

    device = TOTPDevice.objects.get(user=users["manager"], name="admin-totp")
    device.tolerance = 100
    device.save(update_fields=["tolerance"])
    success = client.post(
        ADMIN_MFA_VERIFY_URL,
        {
            "challenge": enrollment.data["challenge"],
            "code": _next_totp_code(device),
        },
        format="json",
    )
    assert success.status_code == 200
    assert success.data["mfa_required"] is False
    assert len(success.data["recovery_codes"]) == settings.ADMIN_MFA_RECOVERY_CODE_COUNT
    access = AccessToken(success.data["access"])
    assert access["admin_auth"] is True
    assert access["admin_session_id"]
    assert access["exp"] - access["iat"] <= 600
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {success.data['access']}")
    assert client.get(ADMIN_ME_URL).status_code == 200
    client.credentials()

    bad_password = client.post(
        ADMIN_LOGIN_URL,
        {"email": "manager@glorybelle.it", "password": "wrong"},
        format="json",
    )
    customer_credentials = client.post(
        ADMIN_LOGIN_URL,
        {"email": "customer@glorybelle.it", "password": "CustomerPass123!"},
        format="json",
    )
    assert bad_password.status_code == customer_credentials.status_code == 401
    assert bad_password.data == customer_credentials.data

    unassigned_staff = User.objects.create_user(
        username="unassigned",
        email="unassigned@glorybelle.it",
        password="UnassignedPass123!",
        is_staff=True,
    )
    denied_staff = client.post(
        ADMIN_LOGIN_URL,
        {"email": unassigned_staff.email, "password": "UnassignedPass123!"},
        format="json",
    )
    assert denied_staff.status_code == 401
    assert denied_staff.data == customer_credentials.data


def _next_totp_code(device):
    step = max(int(time.time()) // device.step, device.last_t + 1)
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = step * device.step
    return str(totp.token()).zfill(device.digits)


@pytest.mark.django_db
def test_mfa_challenge_and_recovery_codes_are_one_time(users):
    client = APIClient()
    enrollment = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    device = TOTPDevice.objects.get(user=users["manager"], name="admin-totp")
    device.tolerance = 100
    device.save(update_fields=["tolerance"])
    first = client.post(
        ADMIN_MFA_VERIFY_URL,
        {
            "challenge": enrollment.data["challenge"],
            "code": _next_totp_code(device),
        },
        format="json",
    )
    assert first.status_code == 200
    assert client.post(
        ADMIN_MFA_VERIFY_URL,
        {
            "challenge": enrollment.data["challenge"],
            "code": _next_totp_code(device),
        },
        format="json",
    ).status_code == 401

    second_login = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    recovery_code = first.data["recovery_codes"][0]
    recovery = client.post(
        ADMIN_MFA_VERIFY_URL,
        {"challenge": second_login.data["challenge"], "code": recovery_code},
        format="json",
    )
    assert recovery.status_code == 200

    third_login = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    reused = client.post(
        ADMIN_MFA_VERIFY_URL,
        {"challenge": third_login.data["challenge"], "code": recovery_code},
        format="json",
    )
    assert reused.status_code == 401


@pytest.mark.django_db
def test_admin_login_lockout_alerts_superuser(users):
    from unittest.mock import patch

    from .security import is_admin_login_locked

    cache.clear()
    client = APIClient()
    payload = {"email": users["manager"].email, "password": "incorrect"}
    with patch("admin_api.security.send_mail", return_value=1) as send_mail:
        for _ in range(settings.ADMIN_LOGIN_FAILURE_LIMIT):
            assert client.post(ADMIN_LOGIN_URL, payload, format="json").status_code == 401
        assert is_admin_login_locked(users["manager"].email)
        send_mail.assert_called_once()
        assert send_mail.call_args.args[3] == [users["superuser"].email]
        assert client.post(
            ADMIN_LOGIN_URL,
            {"email": users["manager"].email, "password": "ManagerPass123!"},
            format="json",
        ).status_code == 401
        send_mail.assert_called_once()
    cache.clear()


@pytest.mark.django_db
def test_admin_sessions_idle_logout_and_password_revocation(users, settings):
    from datetime import timedelta

    from .models import AdminAuthSession

    client = APIClient()
    login = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    device = TOTPDevice.objects.get(user=users["manager"], name="admin-totp")
    device.tolerance = 100
    device.save(update_fields=["tolerance"])
    tokens = client.post(
        ADMIN_MFA_VERIFY_URL,
        {"challenge": login.data["challenge"], "code": _next_totp_code(device)},
        format="json",
    ).data
    session = AdminAuthSession.objects.get(user=users["manager"])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.get(ADMIN_ME_URL).status_code == 200
    assert client.post("/api/admin/logout-everywhere/").status_code == 204
    assert client.get(ADMIN_ME_URL).status_code == 403
    session.refresh_from_db()
    assert session.revoke_reason == "logout_everywhere"

    client.credentials()
    new_login = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    device.refresh_from_db()
    new_tokens = client.post(
        ADMIN_MFA_VERIFY_URL,
        {
            "challenge": new_login.data["challenge"],
            "code": _next_totp_code(device),
        },
        format="json",
    ).data
    active_session = AdminAuthSession.objects.get(
        user=users["manager"], revoked_at__isnull=True
    )
    active_session.last_activity = timezone.now() - timedelta(
        seconds=settings.ADMIN_SESSION_IDLE_TIMEOUT_SECONDS + 1
    )
    active_session.save(update_fields=["last_activity"])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_tokens['access']}")
    assert client.get(ADMIN_ME_URL).status_code == 403
    active_session.refresh_from_db()
    assert active_session.revoke_reason == "idle_timeout"

    client.credentials()
    password_login = client.post(
        ADMIN_LOGIN_URL,
        {"email": users["manager"].email, "password": "ManagerPass123!"},
        format="json",
    )
    device.refresh_from_db()
    password_tokens = client.post(
        ADMIN_MFA_VERIFY_URL,
        {
            "challenge": password_login.data["challenge"],
            "code": _next_totp_code(device),
        },
        format="json",
    ).data
    users["manager"].set_password("NewManagerPass123!")
    users["manager"].save(update_fields=["password"])
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {password_tokens['access']}")
    assert client.get(ADMIN_ME_URL).status_code == 403


@pytest.mark.django_db
def test_login_rate_limit_is_per_ip_and_normalized_email():
    client = APIClient()
    cache.clear()
    payload = {"email": "nobody@glorybelle.it", "password": "wrong"}

    for _ in range(5):
        response = client.post(
            ADMIN_LOGIN_URL, payload, format="json", REMOTE_ADDR="192.0.2.1"
        )
        assert response.status_code == 401
    normalized_case = dict(payload, email="NOBODY@glorybelle.it")
    assert (
        client.post(
            ADMIN_LOGIN_URL,
            normalized_case,
            format="json",
            REMOTE_ADDR="192.0.2.1",
        ).status_code
        == 429
    )
    assert (
        client.post(
            ADMIN_LOGIN_URL,
            payload,
            format="json",
            REMOTE_ADDR="192.0.2.2",
        ).status_code
        == 401
    )
    malformed = client.post(
        ADMIN_LOGIN_URL,
        [],
        format="json",
        REMOTE_ADDR="192.0.2.3",
    )
    assert malformed.status_code == 400
    cache.clear()


@pytest.mark.django_db
def test_admin_refresh_rotates_tokens_and_rejects_customer_refresh(users):
    client = APIClient()
    login = client.post(
        ADMIN_LOGIN_URL,
        {"email": "manager@glorybelle.it", "password": "ManagerPass123!"},
        format="json",
    )
    device = TOTPDevice.objects.get(user=users["manager"], name="admin-totp")
    device.tolerance = 100
    device.save(update_fields=["tolerance"])
    authenticated = client.post(
        ADMIN_MFA_VERIFY_URL,
        {"challenge": login.data["challenge"], "code": _next_totp_code(device)},
        format="json",
    )
    original_refresh = authenticated.data["refresh"]

    response = client.post(
        ADMIN_REFRESH_URL, {"refresh": original_refresh}, format="json"
    )
    assert response.status_code == 200
    assert response.data["refresh"] != original_refresh
    assert AccessToken(response.data["access"])["admin_auth"] is True
    assert (
        client.post(
            ADMIN_REFRESH_URL,
            {"refresh": original_refresh},
            format="json",
        ).status_code
        == 401
    )

    customer_refresh = str(RefreshToken.for_user(users["customer"]))
    rejected = client.post(
        ADMIN_REFRESH_URL, {"refresh": customer_refresh}, format="json"
    )
    assert rejected.status_code == 401
    assert rejected.data["error"]["detail"] == "Credenziali non valide."

    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {str(AccessToken.for_user(users['customer']))}"
    )
    assert client.get(ADMIN_ME_URL).status_code == 403

    users["manager"].groups.clear()
    revoked = client.post(
        ADMIN_REFRESH_URL,
        {"refresh": response.data["refresh"]},
        format="json",
    )
    assert revoked.status_code == 401


@pytest.mark.django_db
def test_audit_is_superuser_only_and_searchable(users, shared_product):
    shared_product.name = "Anello modificato"
    shared_product.save()
    update_change_reason(shared_product, "Nome aggiornato")
    client = APIClient()
    assert client.get(ADMIN_AUDIT_URL, {"model": "product"}).status_code == 401

    client.force_authenticate(user=users["customer"])
    assert client.get(ADMIN_AUDIT_URL, {"model": "product"}).status_code == 403

    client.force_authenticate(user=users["manager"])
    assert client.get(ADMIN_AUDIT_URL, {"model": "product"}).status_code == 403

    client.force_authenticate(user=users["superuser"])
    response = client.get(
        ADMIN_AUDIT_URL,
        {
            "model": "product",
            "object_id": shared_product.pk,
            "search": "Nome",
            "ordering": "-history_date",
        },
    )
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["model"] == "product"
    assert response.data["results"][0]["changed_fields"] == ["name"]

    assert client.get(ADMIN_AUDIT_URL, {"model": "invalid"}).status_code == 400
    assert client.post(ADMIN_AUDIT_URL, {"model": "product"}).status_code == 405
