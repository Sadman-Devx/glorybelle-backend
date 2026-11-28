# GLORYBELLE — deployment checklist

Run through this after every deploy that touches dependencies or environment variables.

## 1. Rebuild with the pinned dependencies
```bash
pip install -r requirements/production.txt     # Docker: docker compose build --no-cache backend celery_worker celery_beat
```
`redis>=6.1,<7` is required: `kombu` 5.7 (pulled in by `celery[redis]`) refuses to work with
older redis-py, which makes **every** `.delay()` raise — no confirmation emails, no invoices,
reservations never expire, and the Stripe webhook answers 500 after the order is already paid.

## 2. Let Django verify the configuration
```bash
python manage.py check --deploy
```
| Id | Meaning |
|---|---|
| `glorybelle.E001` / `E002` | `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` missing or wrong prefix |
| `glorybelle.E003` / `E004` | live secret key with test publishable key (or the reverse) |
| `glorybelle.E005` | Celery's Redis transport unusable (wrong `redis` version) |
| `glorybelle.W001` | `STRIPE_PUBLISHABLE_KEY` missing |
| `glorybelle.W002` | `SENDGRID_API_KEY` missing → confirmation emails fail |
| `glorybelle.W003` | `FATTURA24_API_KEY` missing → no invoices |
| `glorybelle.W004` | `FRONTEND_URL` still points to localhost (broken links in emails) |
| `glorybelle.W005` | `CORS_ALLOWED_ORIGINS` only has localhost origins |
| `glorybelle.W006` | `NUM_PROXIES` is 0; verify it matches the deployment proxy chain |

Errors must be fixed before going live; warnings are acceptable only when the feature is intentionally off.

### Abandoned pending orders
Set `ORDER_PENDING_EXPIRY_MINUTES` to the number of minutes an unpaid pending
order may remain open; the default is `60`. Keep it above the stock reservation
window (`STOCK_RESERVATION_MINUTES`, default `15`) and allow enough time for
Stripe 3DS checkout. When the threshold passes, Celery beat asks Stripe to
cancel each PaymentIntent before marking the order cancelled or releasing that
order's reservations. If Stripe cannot confirm cancellation, the order is left
untouched and retried on a later run.

The Celery worker **and** Celery beat must be running. The
`cancel_expired_pending_orders` task is scheduled every minute and processes at
most 100 orders per run.

### Client IP rate limits
Set `NUM_PROXIES` in `.env` to the number of trusted reverse-proxy hops before Django:
* Direct client-to-Django traffic: `NUM_PROXIES=0`.
* One reverse proxy (nginx or Traefik): `NUM_PROXIES=1`.
* Cloudflare in front of nginx: `NUM_PROXIES=2`.

The value controls which address is selected from `X-Forwarded-For`; configure each
trusted proxy to append or sanitize that header correctly. Keep the default `0` unless
the proxy chain is configured and verified. `check --deploy` reports `glorybelle.W006`
when the value is `0`.

## 3. Stripe
* Dashboard → Developers → Webhooks → endpoint `https://<api-host>/api/webhooks/stripe/`,
  events `payment_intent.succeeded` and `payment_intent.payment_failed`; copy the signing secret to `STRIPE_WEBHOOK_SECRET`.
* The storefront needs the matching **publishable** key in `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`
  (baked in at build time — rebuild the frontend after changing it).

## 4. Smoke test after deploy
1. Place a test order with card `4242 4242 4242 4242`.
2. Order becomes `paid`, stock drops, confirmation email arrives, an `Invoice` row appears.
3. `celery -A config inspect ping` answers; `release_expired_reservations` and
   `cancel_expired_pending_orders` run every minute (celery beat).

## 5. Storefront and API on different domains
Guest carts are identified by the `X-Cart-Token` header (a random token the browser keeps in
localStorage), **not** by a cookie, so they work when the storefront (`shop.example.com`) and the API
(`api.example.com`) are different sites and when the browser blocks third-party cookies.
* `CORS_ALLOWED_ORIGINS` must contain the storefront origin (the header is already allowed:
  `CORS_ALLOW_HEADERS` includes `x-cart-token`).
* The storefront must be built with `NEXT_PUBLIC_API_URL=https://api.example.com`.
* Nothing else is needed — no `SameSite=None` cookie settings.

## Behaviour worth knowing
* **Welcome discount** — a signed-in customer with no completed order gets **10% off ONE product** (a single
  unit of the most expensive item in the cart), applied automatically; the cart (`discount`,
  `total_after_discount`) shows exactly what checkout charges. There is **no expiry**: it still applies a month or a
  year after registering, until the first order is paid. Change the percentage with `FIRST_PURCHASE_DISCOUNT_PERCENT`
  (and an optional minimum basket with `FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL`).
* **Newsletter unsubscribe** — every newsletter e-mail carries its own signed link
  (`<FRONTEND_URL>/newsletter/annulla-iscrizione?token=...`, also sent as a `List-Unsubscribe` header).
  `POST /api/newsletter/unsubscribe/` only accepts that token; a bare e-mail address is rejected.
  Make sure `FRONTEND_URL` is the public storefront URL (`check --deploy` warns otherwise).
  Tokens are signed with `SECRET_KEY`: rotating the key invalidates links in e-mails already sent.
* **Newsletter double opt-in** — new and re-subscribed addresses remain unconfirmed until the
  recipient clicks the signed link at `/newsletter/conferma`; links expire after 7 days.
  Existing active subscribers are grandfathered as confirmed by the newsletter migration.
  Subscribe requests are limited to 5 per IP per hour, and a confirmation email is sent at most
  once per address per `NEWSLETTER_CONFIRMATION_COOLDOWN_MINUTES` (default `15`).
* **First-purchase discount** — a customer holds at most one open (unpaid) discounted order. Starting a new
  checkout cancels the previous pending one, **including its Stripe PaymentIntent**. If that PaymentIntent is
  already paid / processing, the new order is created without the discount (the earlier order already used it).
  If Stripe cannot be reached at that moment, checkout answers `503 payment_unavailable` and the customer simply retries.
* **Webhooks** — an event for an unknown PaymentIntent returns 500 on purpose so Stripe retries it later;
  it is not recorded as processed.
