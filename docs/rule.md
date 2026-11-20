# GLORYBELLE — Engineering Rule Book

**Purpose:** What to avoid and why, across backend, frontend, payments, data, and brand — so future work
doesn't quietly reintroduce a problem this project already solved once.

Each rule states what to avoid, not just what to prefer — a rule without a reason gets worked around the
first time it's inconvenient.

---

## 1. Backend (Django) — Avoid

- **Avoid business logic in `views.py`.** Views should be a thin HTTP adapter. Real logic (stock
  reservation, order creation, payment reconciliation) belongs in each app's `services.py` — untestable,
  unreusable logic buried in a view is how the stock-overselling bug class re-appears.
- **Never touch `ProductVariant.stock_quantity` or `reserved_quantity` outside `select_for_update()`
  inside `transaction.atomic()`.** A "quick fix" that reads-then-writes stock without the lock reopens
  the exact race condition this project already designed around (design doc §6.2).
- **Never trust a client-supplied price, subtotal, or total.** The backend recalculates every amount
  from `ProductVariant.price_override` / `Product.base_price` server-side at checkout. A price sent from
  the frontend is a display value, never an input to charge on.
- **Avoid N+1 queries on list endpoints.** `select_related()` / `prefetch_related()` are mandatory on
  `/api/products/` and anywhere a serializer touches a related object per row — this is invisible at 10
  products and a real outage at 5,000 concurrent users (design doc §6).
- **Never call Stripe, Fattura24, or SendGrid synchronously inside a request/response cycle.** These are
  Celery tasks. A slow or down third party must never make checkout slow or down.
- **Never process a Stripe webhook without checking `ProcessedWebhookEvent` first.** Stripe redelivers
  events; unguarded webhook logic double-processes orders.
- **Avoid `save()` without `update_fields=[...]` when only one or two fields changed.** A full-row save
  under lock contention is unnecessary write amplification at scale.
- **Avoid bare `except:` blocks.** Catch the specific exception you expect; swallowing everything hides
  the exact bugs that matter most in a payment flow.
- **Never store secrets (Stripe key, Fattura24 key, SendGrid key, `SECRET_KEY`) in settings files or
  version control.** Environment variables only, `.env` is git-ignored, `.env.example` documents the
  shape without values.
- **Avoid Django signals for core transactional logic** (order creation, payment status changes). Signals
  are acceptable for side effects like cache invalidation (`catalog/signals.py`), but a signal that's
  secretly part of the checkout flow makes that flow impossible to reason about from `services.py` alone.
- **Never run `makemigrations` and apply it to production without reading the generated migration.**
  Auto-generated migrations occasionally choose a destructive default or an unwanted column type.

## 2. Frontend (Next.js) — Avoid

- **Never treat a frontend-calculated price/total as authoritative.** Display it, but the checkout
  request still gets validated server-side (see backend rule above) — this is a two-sided rule.
- **Avoid storing tokens or payment data in `localStorage`.** Session state belongs server-side (Redis) or
  in an httpOnly cookie; anything in `localStorage` is readable by any injected script.
- **Never hardcode the API base URL or Stripe key in a component.** Both come from
  `NEXT_PUBLIC_API_URL` / `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` — never the Stripe *secret* key, which has
  no reason to exist anywhere in frontend code.
- **Avoid refetching the same data on every render.** Product/category data goes through a caching layer
  (SWR/React Query or Next's built-in fetch cache) — not a fresh `fetch()` in a `useEffect` with no cache
  key.
- **Avoid animation that ignores `prefers-reduced-motion`.** Every scroll-reveal, parallax, and count-up
  effect must check it — already the pattern in the current build; don't add a new animated component
  that skips this check.
- **Avoid inline styles for anything the design system already covers** (color, spacing, type scale).
  Use the tokens in `styles/tokens.css` — a one-off hex value in a component is how the palette drifts.

## 3. Payments & Security — Avoid

- **Never mark an order "paid" from the client-side redirect alone.** The Stripe webhook is the only
  source of truth for payment status (design doc §6.3–6.4). The redirect is for UX, not state.
- **Never create a Stripe PaymentIntent without an idempotency key.** A retried request without one can
  double-charge a customer.
- **Never let raw card data touch GLORYBELLE's servers.** Stripe's hosted Elements/Checkout only — if a
  future requirement seems to need raw card handling, that's a sign the requirement is wrong, not that
  this rule should bend.
- **Never skip Stripe webhook signature verification**, even in a rush to ship a fix — an unverified
  webhook endpoint can be spoofed to mark arbitrary orders paid.
- **Avoid weakening password/auth requirements "temporarily."** Temporary security shortcuts in
  e-commerce auth have a way of becoming permanent.

## 4. Database — Avoid

- **Never delete a `ProductVariant` or `Address` that's referenced by an existing order.** Both use
  `PROTECT` on purpose — order history must stay intact even after a product is discontinued or a
  customer edits their address book.
- **Avoid adding a new frequently-filtered or frequently-joined column without an index.** Check design
  doc §6.5 before adding a field that the shop filters, admin dashboard, or webhook lookup will query on.
- **Never run a schema migration on production without a tested rollback path.**
- **Avoid long-running transactions that hold a row lock.** `select_for_update()` blocks should do the
  minimum work needed (read, check, write) and commit — not sit open while calling an external API.

## 5. Brand & Product Positioning — Avoid

These aren't technical, but they're rules for the same reason the technical ones are — this project
already made a deliberate decision here, and re-adding the removed thing without a conversation first
undoes it silently.

- **Never reintroduce countdown timers, giveaway/contest mechanics, "X left in stock!" urgency badges, or
  installment-payment messaging without an explicit positioning discussion first.** These were removed on
  purpose (see `PRD.md` §1.2, §3.8) as part of the pivot away from mass-market retail tone toward
  boutique-luxury. Re-adding "just one small countdown" is exactly how positioning erodes.
- **Never let trust-building copy drift between surfaces.** The quick-view modal, cart drawer, and chat
  widget must say the same kind of thing the rest of the site says — this project already had to fix one
  inconsistency where mass-retail language survived in the modal after being removed everywhere else.
  Check all three whenever brand copy changes anywhere.
- **Avoid monospace/technical fonts for UI labels, tags, or prices.** Space Mono was deliberately removed
  site-wide in favor of tracked Manrope — a "temporary" monospace addition for a new component reintroduces
  the tech/startup feel this brand doesn't want.
- **Avoid mixing photography styles without a plan.** Product photography should read as one consistent
  shoot (lighting, background, mood) — noted as an open gap in the design review, not a green light to add
  more mismatched stock photos.

## 6. General Engineering Process — Avoid

- **Never claim a fix works without verifying it.** A change to checkout, stock, or payment logic gets
  tested (unit test at minimum; a real browser check for anything UI/scroll/animation-related) before
  it's called done — not assumed correct because the code "looks right."
- **Avoid silently changing a decision that was made deliberately.** If a past decision (a removed
  feature, a chosen library, a positioning choice) seems wrong, raise it — don't quietly reverse it in the
  same change that was supposed to do something else.
- **Never deploy a change to checkout or payment code without load-testing it first**, once the platform
  is live — a correct-looking fix that hasn't been tested under concurrency is exactly the class of bug
  this project spent the most effort preventing (design doc §6).
- **Avoid scope creep disguised as a small fix.** A one-line change to `services.py` that touches stock or
  payment logic gets the same scrutiny as a large one — the size of the diff has never correlated with the
  size of the consequence in this codebase.

---

*Read alongside `PRD.md` (why), `architecture.md` (how it's organized), and the backend design PDF (the
specific mechanisms — locking, idempotency, indexing — that several of these rules protect).*
