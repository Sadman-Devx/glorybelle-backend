# GLORYBELLE — System Architecture

**Version:** 1.0
**Companion documents:** `PRD.md` (product requirements), backend design PDF (database schema & API)

---

## 1. System Architecture

### 1.1 High-Level Overview

GLORYBELLE is a decoupled architecture: a Next.js frontend talks to a Django REST API over HTTPS. The
backend owns all business logic and state; the frontend is a thin, fast rendering layer. No component
talks directly to the database except the Django backend.

```text
                        ┌────────────────────────────────────────────────────────┐                        
                        │                         CLIENT                         │                        
                        │                                                        │                        
                        │          Browser  ·  iOS App  ·  Android App           │                        
                        └────────────────────────────────────────────────────────┘                        
                                                    │                                                     
                                                 │  HTTPS                                                 
                                                    ▼                                                     
                  ┌────────────────────────────────────────────────────────────────────┐                  
                  │                             EDGE / CDN                             │                  
                  │                                                                    │                  
                  │    Cloudflare  —  DNS  ·  edge cache  ·  bot & DDoS protection     │                  
                  └────────────────────────────────────────────────────────────────────┘                  
                                                    │                                                     
                                                    ▼                                                     
      ┌──────────────────────────────────────┐              ┌──────────────────────────────────────┐      
      │               FRONTEND               │              │             BACKEND API              │      
      │                                      │              │                                      │      
      │     Next.js  —  hosted on Vercel     │─────────────▶│             Django + DRF             │      
      │                                      │  REST/JSON   │     Railway  →  AWS ECS Fargate      │      
      │       SSR / SSG product pages        │◀─────────────│                                      │      
      │   cart UI · animations · mega-menu   │              │    business logic · auth · stock     │      
      └──────────────────────────────────────┘              └──────────────────────────────────────┘      
                                                                                         │                
                                                                                         ▼                
   ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐   
   │                                DATA, CACHE  &  EXTERNAL SERVICES                                 │   
   │                                                                                                  │   
   │       PostgreSQL (Milan)       │             Redis              │         Celery workers         │   
   │        system of record        │   cache · sessions · broker    │   email · invoice · cleanup    │   
   │                                                                                                  │   
   ├──────────────────────────────────────────────────────────────────────────────────────────────────┤   
   │                                                                                                  │   
   │             Stripe             │           Fattura24            │     SendGrid / Cloudinary      │   
   │       payment processing       │       e-invoicing (SDI)        │     email / media storage      │   
   └──────────────────────────────────────────────────────────────────────────────────────────────────┘   
```

### 1.2 Component Breakdown

| Component | Role | Notes |
|---|---|---|
| **Next.js frontend** | Renders every customer-facing page; owns UI state (cart drawer open/closed, filter selections, animations, mega-menu). Talks to the backend only through the REST API — never touches the database directly. | Product/category pages use SSG/ISR for SEO and speed; cart/checkout are client-rendered. |
| **Django + DRF backend** | Single source of truth for products, stock, cart, orders, and users. Every business rule (stock reservation, pricing, order status transitions) lives here, not in the frontend. | Stateless — any request can hit any backend instance. |
| **PostgreSQL** | System of record. All durable data: products, orders, users, stock. | Hosted in AWS `eu-south-1` (Milan) for EU data residency and low latency to Italian customers. |
| **Redis** | Three jobs in one: HTTP response cache (product/category listings), Django session store, and the Celery message broker. | A single managed Redis instance is enough at launch; can be split later if needed. |
| **Celery workers** | Run anything the customer shouldn't have to wait for: order-confirmation email, Fattura24 invoice generation, expired-stock-reservation cleanup (see backend design doc §6.11), newsletter sends. | Triggered by the backend, not by the frontend. |
| **Stripe** | Payment processing. Card data never touches GLORYBELLE's servers — the frontend uses Stripe's hosted Elements/Checkout, and the backend only ever sees a PaymentIntent ID. | Source of truth for "was this order actually paid" is the Stripe webhook, not the client redirect. |
| **Fattura24** | Generates and submits Italian electronic invoices (Fatturazione Elettronica / SDI) after an order is marked paid. | Called from a Celery task so a temporary outage doesn't block checkout. |
| **SendGrid** | Transactional email: order confirmation, password reset, newsletter. | |
| **Cloudinary / S3** | Product photography and other media, served through a CDN. | Cloudinary at launch; can migrate to S3 + Cloudflare R2 if bandwidth costs grow. |
| **Cloudflare** | DNS, CDN edge caching for static assets, basic bot/DDoS protection in front of both Vercel and the API. | |
| **Plausible** | Lightweight analytics script loaded on the frontend (`glorybelle-frontend`) — tracks page views and traffic without cookies, so no consent banner is needed. Dashboard accessed separately (Plausible's own hosted UI), not stored in GLORYBELLE's own database. | |

### 1.3 Key Request Flows

**Browsing a category (read-heavy, cached)**
```
Browser → Next.js (SSG/ISR page, often served from Vercel's edge cache)
        → if data is stale: Django /api/products/?category=rings
        → Django checks Redis cache first; on a cache miss, queries PostgreSQL and repopulates Redis
```

**Add to cart**
```
Browser → POST /api/cart/items/ → Django opens a DB transaction,
        locks the ProductVariant row (select_for_update), checks real availability
        (stock − reserved), creates a StockReservation with a 15-minute expiry,
        returns the updated cart
```

**Checkout & payment**
```
Browser → POST /api/checkout/ → Django creates an Order (status=pending) and a Stripe
        PaymentIntent (with an idempotency key) → returns a client_secret
Browser → confirms payment directly with Stripe using the client_secret
Stripe  → sends a payment_intent.succeeded webhook → POST /api/webhooks/stripe/
Django  → verifies the event hasn't been processed before (ProcessedWebhookEvent),
        marks the Order paid, decrements real stock, queues Celery tasks
        (confirmation email, Fattura24 invoice)
```

This webhook-as-source-of-truth pattern means a customer closing their browser tab right after paying
still results in a correctly completed order.

---

## 2. Project Structure

### 2.1 Repository Strategy

Two repositories, deployed independently: `glorybelle-frontend` and `glorybelle-backend`. They are
versioned separately because they scale, deploy, and get worked on at different speeds — the API is
stable and changes rarely; the frontend iterates constantly. Both share the API contract documented in
the backend design PDF.

### 2.2 Frontend — `glorybelle-frontend/` (Next.js)

```
glorybelle-frontend/
├── app/
│   ├── (shop)/
│   │   ├── page.tsx                     # homepage — hero, discover collection, carousel
│   │   ├── prodotti/
│   │   │   ├── page.tsx                 # shop grid + filters
│   │   │   ├── loading.tsx              # skeleton state while filters refetch
│   │   │   └── [slug]/
│   │   │       ├── page.tsx             # product detail (SSG + ISR)
│   │   │       └── opengraph-image.tsx  # per-product social preview image
│   │   ├── carrello/
│   │   │   └── page.tsx                 # cart (client-rendered)
│   │   └── checkout/
│   │       ├── page.tsx
│   │       └── conferma/page.tsx        # order confirmation
│   ├── account/
│   │   ├── layout.tsx                   # auth-gated wrapper
│   │   ├── ordini/
│   │   │   ├── page.tsx                 # order history list
│   │   │   └── [orderNumber]/page.tsx   # order detail
│   │   └── indirizzi/page.tsx           # saved addresses
│   ├── layout.tsx                       # root layout — header, mega-menu, footer, chat widget
│   ├── globals.css
│   ├── not-found.tsx
│   └── sitemap.ts                       # generated from /api/products/ for SEO
│
├── components/
│   ├── hero/
│   │   ├── HeroSticky.tsx               # pinned-background scroll-reveal section
│   │   ├── HeroStats.tsx                # count-up stat numbers
│   │   └── HeroSticky.module.css
│   ├── product/
│   │   ├── ProductCard.tsx              # two-image hover-swap card + dots
│   │   ├── ProductGrid.tsx
│   │   ├── QuickViewModal.tsx           # metal/size selector, price update
│   │   ├── VariantSelector.tsx
│   │   └── ProductFilters.tsx           # sidebar: category, metal, gem, price
│   ├── cart/
│   │   ├── CartDrawer.tsx
│   │   ├── CartItemRow.tsx
│   │   └── CartContext.tsx              # client cart state, synced with the API
│   ├── nav/
│   │   ├── Header.tsx
│   │   ├── MegaMenu.tsx
│   │   └── MobileNav.tsx
│   ├── chat/
│   │   └── ConciergeChat.tsx            # discreet chat widget
│   ├── animation/
│   │   ├── RevealOnScroll.tsx           # IntersectionObserver fade-up/text-reveal wrapper
│   │   └── Parallax.tsx
│   └── ui/                              # shared design system
│       ├── Button.tsx                   # primary / accent / outline variants
│       ├── Input.tsx
│       ├── Pill.tsx
│       └── index.ts                     # barrel export
│
├── lib/
│   ├── api.ts                           # typed fetch wrapper around the Django API
│   ├── stripe.ts                        # Stripe.js client init
│   ├── types.ts                         # shared TS types generated from the OpenAPI schema
│   ├── constants.ts                     # e.g. RESERVATION_MINUTES, PAGE_SIZE
│   └── hooks/
│       ├── useCart.ts
│       ├── useWishlist.ts
│       └── useProductFilters.ts
│
├── public/
│   ├── fonts/
│   └── favicon.ico
│
├── styles/
│   └── tokens.css                       # design tokens: color, type scale, spacing
│
├── next.config.js
├── tsconfig.json
├── package.json
├── .env.local                           # NEXT_PUBLIC_API_URL, Stripe publishable key
└── .env.example
```

### 2.3 Backend — `glorybelle-backend/` (Django)

One Django app per bounded context, matching the model groupings in the backend design doc. Every app
follows the same internal shape so any developer can find their way around a new one immediately.

```
glorybelle-backend/
├── config/                              # project-wide configuration, no business logic
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py                      # shared settings
│   │   ├── local.py                     # DEBUG=True, local Postgres/Redis
│   │   └── production.py                # security headers, allowed hosts, Sentry init
│   ├── urls.py                          # root URLconf — includes each app's urls.py
│   ├── celery.py                        # Celery app instance + autodiscover_tasks()
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── catalog/                         # Category, Product, ProductVariant, ProductImage
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py                     # ProductViewSet, CategoryViewSet
│   │   ├── filters.py                   # django-filter FilterSet: category, metal, gem, price
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── signals.py                   # invalidate Redis cache on Product/Category save
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── cart/                            # Cart, CartItem, StockReservation
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── services.py                  # add_to_cart(): select_for_update + reservation logic
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tasks.py                     # release_expired_reservations (Celery beat, every 1 min)
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── wishlist/                        # Wishlist, WishlistItem
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── orders/                          # Order, OrderItem
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py                     # checkout endpoint, order history/detail
│   │   ├── services.py                  # create_order_from_cart(), snapshot line items
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── payments/                        # Payment, ProcessedWebhookEvent
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── stripe_client.py             # thin wrapper around the Stripe SDK
│   │   ├── views.py                     # POST /api/webhooks/stripe/
│   │   ├── services.py                  # idempotent webhook handling (§6.4 of design doc)
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── invoicing/                       # Invoice
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── fattura24_client.py          # thin wrapper around the Fattura24 API
│   │   ├── tasks.py                     # generate_invoice (Celery task, retries on failure)
│   │   ├── admin.py
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── accounts/                        # CustomerProfile, Address, auth
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py                     # register, me, addresses
│   │   ├── urls.py
│   │   ├── admin.py
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   ├── reviews/                         # Review
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── admin.py                     # is_approved moderation queue
│   │   ├── tests.py
│   │   └── migrations/
│   │
│   └── newsletter/                      # NewsletterSubscriber
│       ├── __init__.py
│       ├── apps.py
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── admin.py
│       ├── tasks.py                     # send via SendGrid
│       ├── tests.py
│       └── migrations/
│
├── core/                                # cross-cutting code shared by every app
│   ├── __init__.py
│   ├── permissions.py                   # IsOwnerOrReadOnly, etc.
│   ├── pagination.py                    # default page_size=8, matches the shop grid
│   ├── exceptions.py                    # OutOfStock and other domain exceptions
│   ├── middleware.py
│   └── cache.py                         # Redis cache key helpers + invalidation utilities
│
├── tests/
│   └── conftest.py                      # shared pytest fixtures (factory_boy factories, API client)
│
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── local.txt                        # + pytest, factory_boy, django-debug-toolbar
│   └── production.txt                   # + gunicorn, sentry-sdk
├── docker-compose.yml                   # local Postgres + Redis for `docker compose up`
├── Dockerfile
├── pytest.ini
└── .env                                 # DB creds, Stripe secret key, Fattura24 key, SendGrid key
```

Each Django app is intentionally self-contained: its `services.py` holds the actual business logic
(e.g. `cart/services.py` owns the `select_for_update` + reservation flow from the backend design doc), so
`views.py` stays a thin HTTP adapter and the same logic is testable and reusable outside of a request —
from `manage.py shell`, a management command, or a Celery task.

### 2.4 Essential Root-Level Files

| File | Purpose |
|---|---|
| `PRD.md` | Product vision, audience, and capability scope (this repo's companion doc). |
| `architecture.md` | This document. |
| `docker-compose.yml` (backend) | Local dev: Django + PostgreSQL + Redis in one command. |
| `.env.example` (both repos) | Documents every required environment variable without committing secrets. |
| `CHANGELOG.md` | Notable changes per release. |

---

## 3. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend framework | **Next.js (React)** | SSR/SSG for SEO on product pages; the interactive UI (mega-menu, cart, animations) already validated in the HTML prototype ports directly to React components. |
| Frontend hosting | **Vercel** | Zero-config Next.js deploys, global edge network. |
| Backend framework | **Django + Django REST Framework** | Mature admin panel for catalog/order management; team's existing expertise. |
| Admin dashboard | **django-unfold** (reskinned Django admin) | Client-facing internal tool for product/image management and viewing customer/order data — reskinned rather than custom-built to keep MVP timeline realistic (see PRD §3.4 and roadmap Day 9). Custom Next.js admin considered as a Phase 2 option post-launch if this proves insufficient. |
| Backend hosting | **Railway/Render** at launch → **AWS ECS Fargate** at scale | Fast to ship first; migrate once traffic justifies the added operational complexity. |
| Database | **PostgreSQL 16** (AWS RDS, `eu-south-1` Milan) | EU data residency, reliable, supports row-level locking (`SELECT ... FOR UPDATE`) used for stock safety. |
| Cache / sessions / broker | **Redis** | Product-listing cache, Django sessions, Celery message broker. |
| Async task queue | **Celery** | Email, invoicing, and stock-reservation cleanup run outside the request/response cycle. |
| Payments | **Stripe** (hosted Elements/Checkout) | PCI scope minimized — card data never reaches GLORYBELLE's servers. |
| Italian e-invoicing | **Fattura24 API** | Generates and submits Fatturazione Elettronica (SDI) — legally required in Italy. |
| Transactional email | **SendGrid** | Order confirmation, password reset, newsletter. |
| Media storage | **Cloudinary** (→ Cloudflare R2 if scale demands) | Image optimization/delivery without managing infrastructure. |
| DNS / CDN | **Cloudflare** | Edge caching, basic bot protection, in front of both Vercel and the API. |
| Connection pooling | **PgBouncer** | Prevents PostgreSQL connection exhaustion under concurrent load (see backend design doc §6.6). |
| Auth | **djangorestframework-simplejwt** | JWT access/refresh tokens for the API. |
| API documentation | **drf-spectacular** (OpenAPI/Swagger) | Living contract between frontend and backend. |
| Monitoring / errors | **Sentry** | Error tracking on both frontend and backend. |
| Analytics | **Plausible (or Fathom)** | Privacy-first, cookie-less visitor/traffic analytics — no EU cookie-consent banner required, unlike GA4. Chosen to match the brand's restrained, trust-first tone rather than default to Google Analytics. |
| Load testing | **Locust** or **k6** | Validates the performance targets in the backend design doc before launch. |

---

*Read alongside `PRD.md` for product scope and the backend design PDF for full database schema, API
contract, and the concurrency/scale strategy referenced above.*
