# GLORYBELLE — Development Roadmap

**Scope:** 3-week build — 2 weeks backend (`glorybelle-backend`), 1 week frontend (`glorybelle-frontend`)
**Reads alongside:** `PRD.md`, `architecture.md`, `design.md`

This roadmap sequences the work so backend correctness (stock, payments, orders) is solid **before**
the frontend wires up against it. Each day lists the concrete deliverable, which app/component it lives
in, and the "done" criteria — so progress is checkable, not just a checkbox.

---

## Phase Overview

| Phase | Duration | Focus | Key Risk Being Managed |
|---|---|---|---|
| **Phase 1 — Backend Foundation & Catalog** | Week 1, Day 1–5 | Project setup, auth, catalog, cart/stock logic | Overselling / race conditions on stock |
| **Phase 2 — Orders, Payments & Hardening** | Week 2, Day 6–10 | Checkout, Stripe, invoicing, testing, deploy | Payment correctness, webhook idempotency |
| **Phase 3 — Frontend Build** | Week 3, Day 11–15 | Port design system into Next.js, wire to live API | Design fidelity to the approved demo/design.md |

**Dependency note:** Frontend static/UI work (tokens, layout shell, component scaffolding) can start
*before* Day 11 if a second person is available — it doesn't need a live API. But cart, checkout,
account, and live product data cannot be wired for real until the backend's OpenAPI contract is frozen
(end of Day 10). This plan assumes one team moving sequentially; compress Phase 3 by ~2 days if frontend
work starts in parallel during Phase 2.

---

## PHASE 1 — Backend Foundation & Catalog (Week 1)

### Day 1 — Project Scaffold
- Initialize `glorybelle-backend` repo per `architecture.md` §2.3 structure (`config/`, `apps/`, `core/`, `tests/`)
- `docker-compose.yml` for local Postgres + Redis (`docker compose up`)
- `config/settings/base.py`, `local.py`, `production.py` split
- Install core deps: Django, DRF, `djangorestframework-simplejwt`, `drf-spectacular`, `django-filter`, `celery`, `redis`, `psycopg2`
- `config/celery.py` — Celery app instance + `autodiscover_tasks()`
- `.env.example` documenting every required variable (DB, Stripe, Fattura24, SendGrid, Cloudinary)
- Sentry SDK wired in `production.py` (no-op locally)
- **Done when:** `docker compose up` + `python manage.py runserver` boots cleanly with an empty DB migrated.

### Day 2 — Catalog Models
- `apps/catalog/`: `Category`, `Product`, `ProductVariant` (metal × size, independent stock per PRD §3.2), `ProductImage`
- `admin.py` registration for all catalog models (this **is** the merchandising tool at launch — no separate CMS)
- Seed script / fixture with sample products matching the demo (Infinity Mini ring, etc.), including a variant with **zero stock** to test the "coming soon" metal case from `design.md` §1.6
- **Done when:** Django admin can create a product with 2+ variants and 2 images (primary + `img2` for the hover-swap card).

### Day 3 — Catalog API
- `serializers.py`, `views.py` (`ProductViewSet`, `CategoryViewSet`)
- `filters.py` — `django-filter` FilterSet: category, metal, gem, price range
- `core/pagination.py` — `page_size=8` (matches the shop grid)
- `core/cache.py` — Redis cache-key helpers; `signals.py` invalidates cache on `Product`/`Category` save
- `drf-spectacular` schema live at `/api/schema/` — this is the contract the frontend will build against in Phase 3
- **Done when:** `GET /api/products/?category=anelli&metal=argento` returns filtered, paginated, cached results — and a second identical request is served from Redis (verify via cache hit log/timing).

### Day 4 — Accounts & Auth
- `apps/accounts/`: `CustomerProfile`, `Address`
- Register / login / refresh / `me` endpoints via `simplejwt`
- `core/permissions.py` — `IsOwnerOrReadOnly` and friends
- Guest-checkout path confirmed at the model level (Order can exist without a user — needed for PRD §3.2 Gift Buyer persona, who may not want an account)
- **Done when:** a user can register, log in, fetch `/api/accounts/me/`, and add/edit an address — all permission-checked.

### Day 5 — Cart & Stock Reservation (highest-risk logic)
- `apps/cart/`: `Cart`, `CartItem`, `StockReservation`
- `services.py` → `add_to_cart()`: `select_for_update()` on the `ProductVariant` row, real-availability check (`stock − reserved`), create a 15-minute `StockReservation`
- `tasks.py` → `release_expired_reservations` (Celery beat, every 1 min)
- Guest session cart + logged-in cart, with a merge-on-login path
- **Done when:** a concurrency test (two simultaneous requests against the last unit of stock) results in exactly one success and one clean `OutOfStock` — not a negative stock count. This is the test to actually run, not just reason about.

**Week 1 exit criteria:** catalog is browsable and filterable via API, auth works, and stock cannot be
oversold under concurrent load. This is the foundation everything else depends on.

---

## PHASE 2 — Orders, Payments & Hardening (Week 2)

### Day 6 — Orders
- `apps/orders/`: `Order`, `OrderItem`
- `services.py` → `create_order_from_cart()` — snapshots line items (price/name at time of purchase, so later catalog edits never retroactively change a past order)
- Checkout endpoint: creates `Order` (`status=pending`)
- **Done when:** hitting checkout with a valid cart produces a `pending` order with correctly snapshotted line items.

### Day 7 — Stripe Payments (webhook-as-source-of-truth)
- `apps/payments/`: `Payment`, `ProcessedWebhookEvent`
- `stripe_client.py` wrapper; checkout endpoint now also creates a Stripe `PaymentIntent` with an idempotency key, returns `client_secret`
- `POST /api/webhooks/stripe/` — verifies `ProcessedWebhookEvent` hasn't seen this event before, marks `Order` paid, decrements **real** stock (converts the reservation into an actual deduction), queues Celery tasks
- **Done when:** replaying the same webhook payload twice (simulate Stripe's at-least-once delivery) results in the order being marked paid exactly once, not double-processed. Also test: close the browser tab immediately after payment — the order must still complete via the webhook alone.

### Day 8 — Invoicing & Email
- `apps/invoicing/`: `Invoice`, `fattura24_client.py`, `tasks.py` → `generate_invoice` (Celery task, retries on failure — a Fattura24 outage must not block checkout, per `architecture.md` §1.2)
- SendGrid order-confirmation email task
- **Done when:** a paid order automatically produces an SDI-compliant invoice and a confirmation email, both fired asynchronously (verify checkout response doesn't wait on either).

### Day 9 — Wishlist, Reviews, Newsletter, Admin Dashboard + Cross-Cutting Cleanup
- `apps/wishlist/` — simple toggle CRUD, persisted per account
- `apps/reviews/` — `Review` model with `is_approved` moderation queue in admin (PRD §3.4 — moderated before publish)
- `apps/newsletter/` — `NewsletterSubscriber`, SendGrid send task
- **Cart abandonment report** (PRD §3.8) — admin-visible report/management command comparing carts created vs. carts converted to a paid `Order` in a given period, using existing `Cart`/`CartItem` data — no new model needed
- **Client admin dashboard** (PRD §3.5) — install and configure `django-unfold`; brand it (logo, primary color from `design.md` palette); customize `ModelAdmin` classes for `Product` (inline `ProductVariant`/`ProductImage` editing with image previews for both `img`/`img2`), `Order` (read-only, clear status), and `CustomerProfile` (order count/total spend as computed `list_display` fields) so the client only sees clean, task-oriented screens — not raw Django defaults
- Confirm `django-cloudinary-storage` is wired as the default file storage, so any image uploaded through the admin lands directly on Cloudinary with no extra step
- Finalize `core/exceptions.py` (`OutOfStock` and friends → consistent API error shape)
- Full `drf-spectacular` schema review — this is the frontend's contract, freeze it today
- **Done when:** OpenAPI schema is complete and stable; cart abandonment numbers for a test period match a manual count; a non-technical person can create a new product with two images through the admin UI without any explanation of Django concepts.

### Day 10 — Testing, Load, and Deploy
- Full `pytest` suite pass (factory_boy fixtures in `tests/conftest.py`)
- Concurrency/idempotency tests from Day 5 & 7 formalized as automated tests, not manual checks
- Load test via Locust/k6 against the cart + checkout flow — validate the PRD's ~5,000-concurrent-user target, tracked by p50/p95/p99, not average
- Deploy to Railway/Render staging; PgBouncer connection pooling confirmed under load
- Sentry verified capturing real errors end-to-end (trigger one intentionally, confirm it appears)
- **Done when:** staging is live, load test results meet target percentiles, and the frontend team has a working staging API URL + published schema to build against.

**Week 2 exit criteria:** a customer can go from empty cart to paid order with an invoice and
confirmation email, with no way to overspend, oversell, or double-charge — and this is proven by tests,
not assumption.

---

## PHASE 3 — Frontend Build (Week 3)

*Design is already finalized (`design.md` + the HTML prototype) — this phase is about faithfully porting
that system into Next.js/React and wiring it to the now-live API, not inventing new design decisions.*

### Day 11 — Scaffold & Design Tokens
- Initialize `glorybelle-frontend` per `architecture.md` §2.2 structure
- `styles/tokens.css` — port the exact color/type/spacing values from `design.md` §2–4 (ivory/emerald/gold palette, Fraunces/Manrope, `140px` section rhythm, card radius scale)
- `lib/api.ts` — typed fetch wrapper generated against the backend's OpenAPI schema; `lib/types.ts` from the same schema
- Root `layout.tsx` — header shell, mega-menu shell, footer, chat widget placeholder
- **Done when:** an empty page renders with correct fonts/colors and a successful authenticated call to `/api/accounts/me/` (or a clean 401) proves the API wrapper works end-to-end.

### Day 12 — Homepage
- `components/hero/HeroSticky.tsx` — pinned-background scroll-reveal, port the 3-image crossfade slideshow behavior from the demo
- `components/hero/HeroStats.tsx` — static numbers (per the design decision to drop the count-up animation — see `design.md` §4.3)
- Discover-Collection editorial cards (`.eg-arch-col` — `14px` radius, per `design.md` §4.6)
- Bestsellers carousel: `ProductCard.tsx` (two-image hover-swap + dots, per `design.md` §4.6.1) inside a horizontal scroll-snap rail, wired to live `/api/products/?featured=true`
- `components/animation/RevealOnScroll.tsx` — IntersectionObserver fade-up wrapper, applied site-wide from here on
- **Done when:** homepage matches the approved demo pixel-for-pixel where it's supposed to, now backed by real API data instead of hardcoded HTML.

### Day 13 — Shop Grid & Product Detail
- `ProductGrid.tsx` + `ProductFilters.tsx` (category/metal/gem/price) — implement the **"coming soon" disabled-filter pattern** from `design.md` §1.6 for any metal/collection with zero stock (e.g. Oro at launch)
- `loading.tsx` skeleton state for the grid (per `design.md` §1.7 — soft ivory pulsing blocks, not generic gray)
- Product detail page (`[slug]/page.tsx`, SSG+ISR) + `opengraph-image.tsx`
- `QuickViewModal.tsx` — `VariantSelector.tsx` (metal/size), live price update, trust signals (certificate, gift packaging, insured shipping)
- **Done when:** a customer can filter, hit an empty/coming-soon state gracefully, open Quick View, and change variants with the price updating live from real stock/price data.

### Day 14 — Cart & Checkout
- `CartContext.tsx` + `CartDrawer.tsx` + `CartItemRow.tsx` — guest + logged-in cart, synced with the backend's reservation system (surface the 15-minute hold to the customer if it's about to expire)
- Checkout page — Stripe Elements/Checkout integration using the `client_secret` from Day 7's endpoint; confirmation page (`conferma/page.tsx`) reflects the *webhook-confirmed* state, not just the client-side redirect
- Basic `account/` section: order history list + detail, saved addresses
- **Done when:** a full real purchase (test-mode Stripe card) completes end-to-end — cart → payment → confirmation page → confirmation email received — matching the webhook-as-source-of-truth flow in `architecture.md` §1.3.

### Day 15 — Polish, Chat, QA & Launch Prep
- `components/chat/ConciergeChat.tsx` — the quiet "Consulente" pill widget from `design.md` §1.5/§4.1
- **Plausible analytics snippet** (PRD §3.8 / `architecture.md` Technology Stack) — added to the root layout, no cookie-consent banner needed since it's cookie-less
- `components/animation/Parallax.tsx` applied to hero/craft imagery; verify `prefers-reduced-motion` is respected everywhere (non-negotiable per both PRD §3.7 and design.md)
- Responsive QA across breakpoints (mobile card stacking, drawer width, mega-menu collapse)
- Lighthouse/performance pass — image optimization via Cloudinary, ISR cache behavior sanity check
- Cross-browser smoke test; Sentry confirmed capturing frontend errors
- Deploy to Vercel; final side-by-side review against `design.md`'s card system and motion tables
- **Done when:** the live Vercel URL matches the approved demo's look and motion timing, backed by the real backend, ready for a client walkthrough.

**Week 3 exit criteria:** a real customer can browse, filter (including hitting a graceful coming-soon
state), quick-view, add to cart, and complete a real payment — on a site that looks and moves exactly
like the approved design — with no placeholder data left anywhere customer-facing.

---

## Cross-Phase Notes

- **Nothing in Phase 3 should require a new design decision.** If the frontend team hits a case not
  covered by `design.md`, that's a signal to pause and add it to the design doc first — not to
  improvise a one-off pattern that drifts from the system (this is exactly the discipline the "coming
  soon" and card-system sections were written to prevent).
- **The out-of-scope list in `PRD.md` §3.8 stays out of scope for this roadmap too** — no countdown
  timers, contest mechanics, or installment-payment badges should appear in any phase above, even as a
  "quick win." Reintroducing them requires a positioning conversation first, not an engineering decision.
- **If a step slips:** protect Day 5 (stock concurrency) and Day 7 (webhook idempotency) above all
  else — these are the two places where a shortcut becomes a real financial/customer-trust problem
  post-launch. Everything else (reviews, newsletter, chat widget polish) can compress or move to a
  fast-follow without the same risk.
