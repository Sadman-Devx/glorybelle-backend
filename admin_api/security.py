import base64
import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import AdminAuthSession, AdminMfaChallenge, AdminRecoveryCode


logger = logging.getLogger(__name__)
User = get_user_model()


def _normalized_identifier(identifier):
    value = str(identifier or "").strip()[:254]
    user = User.objects.filter(email__iexact=value).only("email").first()
    if user is None:
        user = User.objects.filter(username__iexact=value).only("email").first()
    return (user.email or value).strip().casefold() if user else value.casefold()


def _login_cache_keys(identifier):
    normalized = _normalized_identifier(identifier)
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"admin-login-attempts:{digest}",
        f"admin-login-lock:{digest}",
    )


def is_admin_login_locked(identifier):
    _, lock_key = _login_cache_keys(identifier)
    return cache.get(lock_key) is not None


def _send_lockout_alert():
    recipients = list(
        User.objects.filter(is_active=True, is_superuser=True)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    if not recipients:
        logger.error("Admin login lockout occurred without an active superuser email.")
        return

    try:
        sent = send_mail(
            "GLORYBELLE — Blocco temporaneo dell'accesso staff",
            (
                "È stato temporaneamente bloccato un account dell'area amministrativa "
                "dopo ripetuti tentativi di accesso non riusciti. Verifica gli accessi "
                "recenti e contatta il team se non riconosci l'attività."
            ),
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except (OSError, smtplib.SMTPException):
        logger.exception("Could not send admin login lockout alert.")
        return
    if sent != 1:
        logger.error("Admin login lockout alert was not accepted by the email backend.")


def record_admin_login_failure(identifier):
    attempts_key, lock_key = _login_cache_keys(identifier)
    if cache.get(lock_key) is not None:
        return

    window = max(60, settings.ADMIN_LOGIN_LOCKOUT_SECONDS)
    if cache.add(attempts_key, 1, timeout=window):
        attempts = 1
    else:
        try:
            attempts = cache.incr(attempts_key)
        except ValueError:
            cache.set(attempts_key, 1, timeout=window)
            attempts = 1

    if attempts >= settings.ADMIN_LOGIN_FAILURE_LIMIT:
        if cache.add(lock_key, 1, timeout=settings.ADMIN_LOGIN_LOCKOUT_SECONDS):
            _send_lockout_alert()


def clear_admin_login_failures(identifier):
    attempts_key, lock_key = _login_cache_keys(identifier)
    cache.delete_many((attempts_key, lock_key))


def issue_admin_mfa_challenge(user, purpose):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now = timezone.now()
    AdminMfaChallenge.objects.filter(
        user=user,
        consumed_at__isnull=True,
    ).update(consumed_at=now)
    AdminMfaChallenge.objects.filter(expires_at__lte=now).delete()
    AdminMfaChallenge.objects.create(
        user=user,
        token_hash=token_hash,
        purpose=purpose,
        expires_at=now + timedelta(seconds=settings.ADMIN_MFA_CHALLENGE_TTL_SECONDS),
    )
    return raw_token


def find_admin_mfa_challenge(raw_token, purpose=None, lock=False):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    challenges = AdminMfaChallenge.objects.select_related("user")
    if lock:
        challenges = challenges.select_for_update()
    filters = {
        "token_hash": token_hash,
        "consumed_at__isnull": True,
        "expires_at__gt": timezone.now(),
    }
    if purpose:
        filters["purpose"] = purpose
    return challenges.filter(**filters).first()


def admin_totp_device(user, confirmed=None):
    devices = TOTPDevice.objects.filter(user=user, name="admin-totp")
    if confirmed is not None:
        devices = devices.filter(confirmed=confirmed)
    return devices.order_by("pk").first()


def admin_totp_provisioning_details(device):
    secret = base64.b32encode(bytes.fromhex(device.key)).decode("ascii").rstrip("=")
    label = quote(f"GLORYBELLE:{device.user.email or device.user.get_username()}")
    issuer = quote("GLORYBELLE")
    uri = (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={device.digits}"
        f"&period={device.step}"
    )
    return {"secret": secret, "provisioning_uri": uri}


def _recovery_code_hash(user, code):
    normalized = code.replace("-", "").replace(" ", "").upper()
    payload = f"admin-recovery:{user.pk}:{normalized}".encode("utf-8")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def replace_admin_recovery_codes(user):
    AdminRecoveryCode.objects.filter(user=user, used_at__isnull=True).update(
        used_at=timezone.now()
    )
    codes = []
    for _ in range(settings.ADMIN_MFA_RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(6).upper()
        code = f"{raw[:6]}-{raw[6:]}"
        codes.append(code)
        AdminRecoveryCode.objects.create(
            user=user,
            code_hash=_recovery_code_hash(user, code),
        )
    return codes


def _consume_admin_recovery_code(user, code):
    return (
        AdminRecoveryCode.objects.filter(
            user=user,
            code_hash=_recovery_code_hash(user, code),
            used_at__isnull=True,
        ).update(used_at=timezone.now())
        == 1
    )


def verify_admin_mfa_code(user, code):
    normalized = str(code or "").strip().upper()
    device = admin_totp_device(user, confirmed=True)
    if device is None:
        return None

    if len(normalized) == device.digits and normalized.isdigit():
        return device if device.verify_token(normalized) else None
    if _consume_admin_recovery_code(user, normalized):
        return device
    return None


def create_admin_auth_session(user):
    return AdminAuthSession.objects.create(user=user)


def get_active_admin_session(user, session_id, touch=False):
    try:
        session = AdminAuthSession.objects.get(
            user=user,
            session_id=session_id,
            revoked_at__isnull=True,
        )
    except (
        AdminAuthSession.DoesNotExist,
        DjangoValidationError,
        ValueError,
        TypeError,
    ):
        return None

    if (
        not user.is_active
        or not user.is_staff
        or admin_totp_device(user, confirmed=True) is None
    ):
        AdminAuthSession.objects.filter(
            pk=session.pk,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now(), revoke_reason="account_changed")
        return None

    now = timezone.now()
    idle_limit = timedelta(seconds=settings.ADMIN_SESSION_IDLE_TIMEOUT_SECONDS)
    if now - session.last_activity >= idle_limit:
        AdminAuthSession.objects.filter(
            pk=session.pk,
            revoked_at__isnull=True,
        ).update(revoked_at=now, revoke_reason="idle_timeout")
        return None
    if touch:
        updated = AdminAuthSession.objects.filter(
            pk=session.pk,
            revoked_at__isnull=True,
        ).update(last_activity=now)
        if not updated:
            return None
        session.last_activity = now
    return session


def revoke_admin_session(session_id, user, reason="logout"):
    return AdminAuthSession.objects.filter(
        user=user,
        session_id=session_id,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now(), revoke_reason=reason)


def revoke_user_admin_sessions(user, reason):
    return AdminAuthSession.objects.filter(
        user=user,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now(), revoke_reason=reason)


@transaction.atomic
def consume_admin_mfa_challenge(challenge):
    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["consumed_at"])
