"""Signed, tamper-proof links for newsletter subscription management.

The token is the subscriber's e-mail signed with the project SECRET_KEY (HMAC), so only a
link we generated for that address can unsubscribe it — knowing someone's e-mail address
is no longer enough to unsubscribe them. It deliberately has NO expiry: an unsubscribe link
in an old e-mail must keep working (and the law expects it to).
"""
from datetime import timedelta

from django.conf import settings
from django.core import signing

UNSUBSCRIBE_SALT = "glorybelle.newsletter.unsubscribe"
CONFIRMATION_SALT = "glorybelle.newsletter.confirmation"
CONFIRMATION_MAX_AGE = int(timedelta(days=7).total_seconds())


class ConfirmationTokenExpired(Exception):
    """The signed confirmation link exceeded its allowed lifetime."""


def make_unsubscribe_token(email: str) -> str:
    return signing.dumps(email.strip().lower(), salt=UNSUBSCRIBE_SALT, compress=True)


def read_unsubscribe_token(token: str) -> str | None:
    """Return the e-mail the token was issued for, or None if it is forged / corrupted."""
    try:
        value = signing.loads(token, salt=UNSUBSCRIBE_SALT)
    except signing.BadSignature:
        return None
    return value if isinstance(value, str) and value else None


def make_confirmation_token(email: str, nonce: str) -> str:
    return signing.dumps(
        {"email": email.strip().lower(), "nonce": str(nonce)},
        salt=CONFIRMATION_SALT,
        compress=True,
    )


def read_confirmation_token(token: str) -> dict[str, str] | None:
    """Read a valid, unexpired confirmation token; distinguish expiry from forgery."""
    try:
        value = signing.loads(
            token,
            salt=CONFIRMATION_SALT,
            max_age=CONFIRMATION_MAX_AGE,
        )
    except signing.SignatureExpired as exc:
        raise ConfirmationTokenExpired from exc
    except signing.BadSignature:
        return None

    if (
        isinstance(value, dict)
        and isinstance(value.get("email"), str)
        and isinstance(value.get("nonce"), str)
    ):
        return value
    return None


def confirmation_url(email: str, nonce: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    token = make_confirmation_token(email, nonce)
    return f"{base}/newsletter/conferma?token={token}"


def unsubscribe_url(email: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/newsletter/annulla-iscrizione?token={make_unsubscribe_token(email)}"
