"""
Signed, tamper-proof unsubscribe links.

The token is the subscriber's e-mail signed with the project SECRET_KEY (HMAC), so only a
link we generated for that address can unsubscribe it — knowing someone's e-mail address
is no longer enough to unsubscribe them. It deliberately has NO expiry: an unsubscribe link
in an old e-mail must keep working (and the law expects it to).
"""
from django.conf import settings
from django.core import signing

SALT = "glorybelle.newsletter.unsubscribe"


def make_unsubscribe_token(email: str) -> str:
    return signing.dumps(email.strip().lower(), salt=SALT, compress=True)


def read_unsubscribe_token(token: str) -> str | None:
    """Return the e-mail the token was issued for, or None if it is forged / corrupted."""
    try:
        value = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        return None
    return value if isinstance(value, str) and value else None


def unsubscribe_url(email: str) -> str:
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/newsletter/annulla-iscrizione?token={make_unsubscribe_token(email)}"
