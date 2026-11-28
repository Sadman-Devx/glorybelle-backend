"""
Guest-cart identification that does NOT depend on cookies.

Why: the storefront and the API usually live on different domains in production
(e.g. shop.example.com + api.example.com, or *.vercel.app + an API host). A session
cookie set by the API is then a *cross-site* cookie: `SameSite=Lax` stops browsers
from sending it on the storefront's fetch() calls, and Safari / Firefox / Chrome
block third-party cookies altogether — so guest carts silently vanish.

Instead the browser generates a random, unguessable token (128 bits), keeps it in
localStorage and sends it as the ``X-Cart-Token`` header. The token is a bearer secret
for ONE guest cart. The Django session cookie keeps working as a fallback for
clients that do not send the header (old tabs, API tools, existing carts).
"""
import re

CART_TOKEN_HEADER = "X-Cart-Token"
KEY_PREFIX = "gt_"  # Cart.session_key is max_length=40 -> prefix(3) + token(32)
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def guest_cart_key(request) -> str | None:
    """Return the Cart.session_key for the request's X-Cart-Token, or None if absent/malformed."""
    raw = (request.headers.get(CART_TOKEN_HEADER) or "").strip().lower()
    return f"{KEY_PREFIX}{raw}" if _TOKEN_RE.fullmatch(raw) else None
