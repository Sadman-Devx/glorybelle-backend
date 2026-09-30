# GLORYBELLE — Product Requirements Document

**Version:** 1.0
**Market:** Italy (EU expansion planned)
**Status:** Design complete — backend build in progress

---

## 1. Product Vision

### 1.1 Statement

GLORYBELLE is a quiet-luxury jewelry brand and e-commerce platform for the Italian market. Every piece is
hallmarked, hand-finished, and made from recycled 18K gold and traceable stones — sold through a digital
experience that feels like an editorial boutique, not a discount marketplace.

### 1.2 Positioning

GLORYBELLE sits deliberately between two existing market models, and rejects both extremes:

| | Mass-market jewelry retail (e.g. Stroili) | GLORYBELLE | Ultra-high luxury houses (e.g. Cartier) |
|---|---|---|---|
| Price point | Accessible, high-volume | Accessible premium | Inaccessible to most |
| Marketing tone | Countdown timers, contests, installment-payment badges everywhere | Calm, editorial, storytelling-led | Sparse, gallery-like |
| Digital experience | Busy, promo-heavy | Warm, spacious, considered | Minimal to the point of cold |

The founding design decision of this product (documented across the build) was a deliberate pivot **away**
from mass-retail marketing tactics (flash-sale countdowns, giveaway contests, installment-payment
messaging, aggressive sale badges) toward a **boutique-luxury** tone: generous whitespace, heritage
storytelling, a single confident call to action per screen, and trust built through craftsmanship narrative
rather than urgency or discounting.

### 1.3 Why now

Italian jewelry e-commerce is dominated by mass-market chains built for volume. There is a gap for a
**digitally-native boutique brand** — one that never opened a physical store first, built entirely around
an editorial online experience, and treats the website itself as the flagship "store."

### 1.4 Success looks like

- A customer can browse, fall in love with a piece, and check out in a mood that never breaks — no
  discount pop-ups, no manufactured urgency.
- The brand reads as established and considered even as a new entrant, through craft storytelling,
  photography, and restrained motion design.
- The platform performs reliably at real commercial scale (concurrent shoppers, simultaneous checkouts)
  without the customer ever perceiving the underlying complexity.

---

## 2. Target Audience

### 2.1 Primary persona — "The Considered Buyer"

- **Who:** Women, roughly 28–45, based in major Italian cities (Milano, Roma, Torino) or affluent
  suburbs. Comfortable spending €100–300 on a piece she'll wear often, without needing a special
  occasion to justify it.
- **Values:** Quality and provenance over logo status. Reads product descriptions. Notices whether a
  site *feels* trustworthy before she notices the price.
- **Turn-offs:** Countdown timers, "only 2 left!" pressure tactics, pop-up giveaways — these actively
  erode trust for this buyer rather than converting her.
- **What earns her trust:** Real material information (18K, recycled gold, traceable stones), a
  certificate of authenticity, gift packaging, and a site that *looks* like the brand's values are true.

### 2.2 Secondary persona — "The Gift Buyer"

- **Who:** Partners or family members buying jewelry as a gift — often less familiar with jewelry
  terminology, more anxious about getting it right (size, whether she'll like it).
- **Needs:** Clear size guidance, an easy quick-view of options, a confident "gift-ready" signal
  (packaging, easy returns/resizing), and a fast, low-friction checkout since this is often a
  time-pressured purchase (anniversary, birthday) — even though the *brand tone* stays calm.

### 2.3 Tertiary — "The Returning Collector"

- **Who:** Existing customers building a small personal collection over time (stacking rings, layered
  necklaces). Higher lifetime value, lower price sensitivity per visit.
- **Needs:** Easy re-discovery of past purchases, wishlist, notification of new collections — not
  discount incentives.

### 2.4 Explicitly *not* the audience

- Bargain-hunters motivated primarily by sale percentage — the mass-retail-pivot decision means GLORYBELLE
  does not compete on this basis, and product/marketing decisions should not be second-guessed to chase
  this segment.

---

## 3. Key Capabilities

### 3.1 Discovery & Browsing
- Full-bleed cinematic hero with a pinned/sticky scroll-reveal effect (background stays fixed while
  hero content and stats rise over it)
- Mega-menu navigation with category, metal, gem, and price quick-filters plus a category promo image
- "Discover the Collection" editorial cards (large photography, overlaid category CTA)
- Full shop grid with sidebar filtering (category, metal, gem, price) and sort
- Two-image hover-swap product cards with pagination dots
- Trending/carousel product rail
- "Load more" progressive pagination

### 3.2 Product Experience
- Product variants by metal (18K gold / rose gold / sterling silver) and size, each with independent
  stock
- Quick-view modal: metal swatch selector, size selector, price updates live, trust signals
  (certificate of authenticity, gift packaging, insured shipping)
- Wishlist (heart toggle, persisted per account)
- Product image gallery sourced from a consistent photographic direction

### 3.3 Cart & Checkout
- Persistent cart (guest session + logged-in, merged on login) showing selected metal/size per line
  item
- Real-time stock visibility that accounts for other shoppers' in-progress carts (stock-reservation /
  cart-hold pattern — see backend design doc §6.11), so customers are never shown false availability
- Stripe-based payment, PCI scope minimized via hosted payment elements
- Italian electronic invoicing (Fatturazione Elettronica / SDI) generated automatically per paid order
- Order confirmation and status via email

### 3.4 Account & Trust
- Register / login / guest checkout
- Saved addresses, order history
- Newsletter signup (editorial/early-access framing, not discount-bait)
- Customer reviews, moderated before publish
- Discreet concierge-style chat (framed as "GLORYBELLE Consultant," not a live-chat sales bot)

### 3.5 Internal Operations & Admin
- **Client-operable admin dashboard** — the client is non-technical, so the standard Django admin is
  reskinned (via django-unfold) rather than exposed raw: clear "Add Product" / "Upload Photo" flows,
  branded to feel like part of the GLORYBELLE product rather than a developer tool
- Product creation and editing, including uploading both card images (primary + hover-alternate, per
  the two-image product card pattern in the design doc) directly through the dashboard, with automatic
  optimized delivery via Cloudinary — no code or developer involvement needed for routine catalog updates
- Customer and order visibility (who bought what, order status, contact info) for day-to-day operations
- **Scoped to launch needs deliberately** — a fully custom-built Next.js admin app is a real option, but
  deferred to a Phase 2 decision post-launch, made only if the reskinned admin proves insufficient in
  practice, rather than speculatively built into the MVP timeline

### 3.6 Brand & Content
- Craft/heritage storytelling section (sourcing → casting → certification), paired with real
  photography, not just icons
- Testimonials
- Instagram content grid
- Consistent Italian-language copy throughout (EUR pricing, Italian address/phone formats)

### 3.7 Motion & Interaction Design
- Scroll-triggered reveal animations (fade-up, text mask-reveal)
- Parallax on key photography
- All animation restrained and purposeful — reinforces the boutique tone rather than "flash-y" — and
  respects `prefers-reduced-motion`

### 3.8 Analytics & Reporting
- **Site traffic** — daily/weekly visitor counts via a privacy-first analytics tool (no cookie-consent
  banner required — see architecture doc), so traffic can be monitored without adding a tracking popup
  that would undercut the brand's trust-first tone.
- **Cart abandonment reporting** — using the existing `Cart`/`CartItem` data (§3.3), report how many
  carts were created in a period versus how many converted to a paid `Order`, surfaced in the admin so
  the team can see "added to cart but didn't buy" volume without a separate analytics tool.

### 3.9 Platform Reliability (non-functional, but core to the product promise)
- Designed for ~5,000 concurrent users without correctness failures (no overselling, no duplicate
  charges) — see backend design doc for indexing, locking, idempotency, and caching strategy
- Realistic performance targets tracked by percentile (p50/p95/p99), not a single average
- Async processing for anything the customer isn't directly waiting on (confirmation email, invoice
  generation)

### 3.10 Explicitly out of scope (for this phase)
- Flash-sale countdown mechanics, giveaway/contest campaigns, tiered discount badges — removed by
  deliberate positioning decision (§1.2), not a gap to be filled later without a positioning
  conversation first
- Buy-now-pay-later / installment payment messaging — reconsider only if positioning shifts back toward
  mass-market
- Physical store / click-and-collect logistics — GLORYBELLE is digitally-native; no physical retail network
  exists to integrate with

---

*This document reflects product decisions made through iterative design of the GLORYBELLE storefront and
should be read alongside the accompanying backend technical design document (database schema & API).*
