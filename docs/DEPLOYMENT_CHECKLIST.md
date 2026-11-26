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

Errors must be fixed before going live; warnings are acceptable only when the feature is intentionally off.

## 3. Stripe
* Dashboard → Developers → Webhooks → endpoint `https://<api-host>/api/webhooks/stripe/`,
  events `payment_intent.succeeded` and `payment_intent.payment_failed`; copy the signing secret to `STRIPE_WEBHOOK_SECRET`.
* The storefront needs the matching **publishable** key in `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`
  (baked in at build time — rebuild the frontend after changing it).

## 4. Smoke test after deploy
1. Place a test order with card `4242 4242 4242 4242`.
2. Order becomes `paid`, stock drops, confirmation email arrives, an `Invoice` row appears.
3. `celery -A config inspect ping` answers; `release_expired_reservations` runs every minute (celery beat).

## Behaviour worth knowing
* **First-purchase discount** — a customer holds at most one open (unpaid) discounted order. Starting a new
  checkout cancels the previous pending one, **including its Stripe PaymentIntent**. If that PaymentIntent is
  already paid / processing, the new order is created without the discount (the earlier order already used it).
  If Stripe cannot be reached at that moment, checkout answers `503 payment_unavailable` and the customer simply retries.
* **Webhooks** — an event for an unknown PaymentIntent returns 500 on purpose so Stripe retries it later;
  it is not recorded as processed.
