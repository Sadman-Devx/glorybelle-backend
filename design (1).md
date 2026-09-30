# GLORYBELLE — Design System
*Luxury Italian Jewelry E-Commerce — Design Documentation*

This document captures the design decisions already implemented in the demo, plus additional recommendations to push the brand further toward a genuine luxury feel in production.

---

## 1. User Experience (UX)

### 1.1 Core Principle
Luxury UX is built on **restraint, not features**. Every interaction in this demo is intentionally slow, quiet, and confident — never gamified, urgent, or "salesy." The goal is a customer who feels like they've walked into a private atelier, not a discount storefront.

### 1.2 Navigation Flow
- **Sticky top nav** — logo centered, primary categories left/right, utility icons (search, wishlist, cart) right-aligned. Nav stays minimal: no mega-menus with dozens of links.
- **Announcement bar** — rotates every 4s between heritage/shipping/event messages, never discount-driven. Fades between messages (0.5s), never hard-cuts.
- **Hero → Trust strip → Featured carousel → Product grid → Craft story → Testimonials → Instagram grid → Footer** — a storytelling sequence, not just a product dump. Craft/heritage content is placed *before* the customer is asked to buy anything else, building trust first.

### 1.3 Product Discovery
- **Horizontal scroll-snap carousel** for "Più venduti" (bestsellers) — swipeable, no jarring pagination dots.
- **Filterable grid** (category, metal, gem, price, sort) — filters are quiet dropdowns/links, not aggressive colored pills. **Desktop-only** as an always-visible sidebar — see §1.3.1 for the mobile/tablet pattern, which is deliberately different.
- **Quick View modal** — lets a customer preview a product without leaving the page context (critical for reducing friction on a luxury purchase decision).
- **Wishlist (heart icon)** — persistent across session, colored rosewood when active — a small, elegant signal rather than a loud badge/counter.

### 1.3.1 Responsive Filter Pattern (Mobile & Tablet)
The desktop sidebar (Category / Metal / Stone / Price, always expanded) works because there's horizontal
room for it beside the grid. Below `1024px` that room disappears — an always-expanded sidebar stacks
*above* the product grid instead of beside it, pushing every product below a wall of filter options the
customer has to scroll past before seeing a single piece of jewelry. This is a real, measurable UX cost
(the thing the customer came for is the last thing they see), so mobile and tablet get a **different
pattern**, not a squeezed version of the same one.

**Breakpoint behavior:**

| Breakpoint | Pattern |
|---|---|
| Desktop (`≥1024px`) | Unchanged — sidebar as-is, always expanded beside the grid |
| Tablet (`768–1023px`) | Same drawer pattern as mobile (see below) — the existing 2-column card grid (`design.md` §4.6) is already tight at this width, so a persistent sidebar would cramp it further with no real benefit over the drawer |
| Mobile (`<768px`) | Drawer pattern (see below) |

**The pattern itself, replacing the stacked sidebar below `1024px`:**

1. **Filter trigger row** — a compact row sits where the sidebar used to be, at the top of the grid, same line as "Showing all 12 jewels" / the sort dropdown. A single **pill-shaped "Filtra" button** (same shape/weight language as the `Consulente` button, §4.1) opens the filter panel. When one or more filters are active, the button shows a count — `Filtra (2)` — so the customer knows something is already applied without opening the panel.
2. **Bottom-sheet drawer, not full-screen** — tapping "Filtra" slides a panel up from the bottom of the screen (`translateY`, `.35s cubic-bezier(.22,.68,.3,1)` — the same easing already used for the cart drawer and Quick View modal, §4.3), covering roughly 80–85% of the viewport height rather than 100%. Leaving a sliver of the product grid visible above it keeps the customer oriented — they never fully leave the shopping context, which matters for the "mood that never breaks" checkout principle in the PRD.
3. **Accordion inside the drawer** — Category / Metal / Stone / Price are collapsed sections inside the drawer (one open at a time), not all expanded at once. This is what actually solves the scroll problem — the drawer itself never needs to scroll more than one section's worth of options.
4. **Sticky footer inside the drawer** — a "Clear all" text link (top-left of the drawer) and a primary button at the bottom — `Mostra 8 risultati` — with the result count updating live as the customer selects filters, before they even close the drawer.
5. **Applied-filter chips on the grid** — once the drawer is closed, active filters appear as small dismissable chips above the grid (`18K Oro ✕`, `Sotto €100 ✕`), so the customer can see and remove individual filters without reopening the full drawer. Chips use the same hairline-border, `3px`-radius language as the smallest cards in §4.6, keeping them visually minor rather than competing with the products.

**Why a bottom sheet and not a full-screen takeover:** a full-screen filter page reads as a "different
screen" the customer has left and must return from — closer to a settings menu than a boutique
experience. A bottom sheet that leaves the grid peeking out above it reads as an *overlay on* the
shopping experience, not an exit from it — consistent with why the cart is a drawer and Quick View is a
modal rather than either being a separate page (§1.4).

### 1.4 Cart & Checkout Feel
- **Slide-in cart drawer** (not a full page redirect) — keeps the customer inside the immersive brand experience.
- **Toast notifications** for "added to cart" — appears bottom-center, auto-dismisses in 2.6s, no intrusive modal interruption.
- Trust row (shipping/returns/certification) shown *inside* the drawer and modal — reassurance exactly at the moment of hesitation.

### 1.5 Micro-Consultation Layer
- **"Consulente" chat widget** — reframed from a generic bouncy support bubble into a quiet, pill-shaped invitation for private consultation — matching how a real boutique associate would approach a customer (present, not pushy).

### 1.6 Handling Unavailable Categories / "Coming Soon" States
A common early-stage situation: not every metal/collection (e.g. **Oro / Gold**) may be in stock or photographed yet at launch. This should never result in a broken filter or an empty grid — it should feel like an intentional, upcoming reveal, not a gap.

**Pattern to use:**
- **Disable the filter option itself**, don't hide it. Show "Oro" in the metal filter at reduced opacity (~40%) with a small `Prossimamente` (Coming Soon) tag beside it in `gold-deep`, uppercase, 10px, letter-spacing `.08em` — same visual language as the eyebrow/tag labels used elsewhere on the site.
- The disabled filter button should not be clickable (`pointer-events: none` or a `disabled` state) — or, if clicked, show a brief non-blocking tooltip: *"Disponibile a breve"*.
- **If a customer lands directly on an unavailable category** (via an old link, email campaign, etc.), show a full branded empty-state instead of a blank page:
  - Same background/typography system (ivory background, Fraunces heading, thin gold divider)
  - A simple line-art icon (e.g. a ring outline) — no stock photo filler
  - Heading: *"La collezione Oro sta arrivando"*
  - One line of supporting copy: *"Stiamo lavorando a qualcosa di speciale."*
  - A single email field + button (*"Avvisami"*) to capture the customer as a waitlist lead rather than losing them — this turns an unavailable-inventory moment into a lead-gen opportunity.
- **Never** use a default framework "404" or "No results found" message here — it should read as deliberate brand pacing ("we're not ready to show you this yet"), not a technical error.

### 1.7 Recommended Additions for Production
- **Skeleton loading states** — not yet implemented in the demo. Before real backend data loads (product grid, cart, quick view), show soft pulsing placeholder blocks in the ivory/line palette instead of a blank flash or spinner. This is a *must* for perceived performance and polish on a real e-commerce backend.
- **Empty states** — a designed empty cart / empty wishlist / no-results state (currently placeholder-level), styled with the same restraint as the rest of the site.
- **Ring size guide** — an inline sizer/guide modal, since sizing anxiety is a top purchase blocker for jewelry specifically.
- **Order confirmation & tracking UX** — should carry the same visual language (Fraunces headlines, gold accents) rather than defaulting to a generic payment-provider template.
- **Micro-copy pass** — every button, error, and confirmation message should be reviewed in Italian for tone (formal "Lei" register, warm but composed — never exclamation-heavy).

---

## 2. Colour & Visual Theme

### 2.1 Palette (from the live CSS variables)

| Token | Hex | Usage |
|---|---|---|
| `--ink` | `#2E1A47` | Primary text, dark backgrounds (footer, craft section) |
| `--ivory` | `#F7F2FC` | Primary page background |
| `--ivory-2` | `#ECE0F8` | Secondary/alternate section background |
| `--gold` | `#E5B80B` | Primary accent (buttons, icons) |
| `--gold-light` | `#F4D35E` | Accent on dark backgrounds, hover highlights |
| `--gold-deep` | `#A8790A` | Tags, labels, small eyebrow text |
| `--emerald` | `#2C4E9C` | Secondary brand color, active states |
| `--emerald-deep` | `#16264A` | Primary buttons, chat widget, dark UI elements |
| `--rosewood` | `#7C3AAD` | Wishlist "active" state only — used sparingly as an emotional accent |
| `--line` | `rgba(46,26,71,.13)` | Hairline dividers |
| `--line-strong` | `rgba(46,26,71,.22)` | Borders needing more definition (outline buttons) |

> **Note on naming:** token names in the codebase are unchanged (`--gold`, `--emerald`, `--rosewood`, etc.) even though the hues behind them moved — `--emerald` now renders as a sapphire blue and `--rosewood` as an amethyst violet, not their literal namesakes. This keeps the CSS diff small, but anyone new to the codebase should read this table rather than assume the variable name describes the current color.

### 2.2 Design Philosophy
- **Cool neutrals over pure white/black.** Ivory shifted from a warm cream to a pale lavender-white — it still keeps the palette soft and "paper-like" rather than reading as a tech interface, but the undertone is now amethyst instead of stationery-cream.
- **Sapphire, amethyst and citrine, not black + gold.** This is a deliberate departure both from the black/gold luxury cliché and from the original muted emerald/gold identity. `--emerald` now renders as a rich sapphire blue and `--rosewood` as a saturated amethyst violet; paired with a true yellow-gold `--gold`, the three read as a jeweled trio rather than a single metal-plus-stone accent — still distinctly upscale, but bolder and more contemporary than the original botanical green.
- **Rosewood is still a single-purpose accent** — same rule as before: reserved only for the wishlist "loved" state, so the new violet stays a special-occasion moment rather than becoming a third background color.
- **More saturated than the original palette — by design, not by accident.** The original palette used desaturation as its main restraint mechanism; this palette trades some of that muting for clearer jewel-tone identity (true blue, true violet, true yellow). To keep the luxury feel intact, that saturation needs to stay concentrated in small accent moments — icons, buttons, eyebrow labels, the wishlist heart — while `--ivory`/`--ivory-2` continue to carry every large surface. The restraint now lives in the *ratio* of color to neutral space rather than in how muted each individual color is.

### 2.3 Recommended Refinement
- Introduce a **cool stone neutral** — a soft lilac-grey (e.g. `#DED4EC`) — as a tertiary background option for section breaks. It plays the same role a travertine greige would have played for the original warm palette, but tuned to sit comfortably next to the new violet/sapphire/citrine accents instead of fighting them.
- Keep all future accent colors (badges, banners, promo callouts) restricted to this existing palette — resist adding new "brand colors" per campaign, which is a common way discount-brand energy creeps back in.

---

## 3. Typography

### 3.1 Typeface Pairing
- **Display / Headings — [Fraunces](https://fonts.google.com/specimen/Fraunces)** (serif, weight 500, optical sizing 9..144). A soft, editorial serif with warmth — avoids the coldness of a strict didone (like Didot) while still feeling premium and European.
- **Body / UI / Labels — [Manrope](https://fonts.google.com/specimen/Manrope)** (sans-serif, weights 400–800). Clean and neutral, so it never competes with Fraunces for attention — it exists to support, not to speak.

### 3.2 Scale & Usage

| Element | Font | Size | Weight | Notes |
|---|---|---|---|---|
| Hero title | Fraunces | `clamp(38px, 5.2vw, 64px)` | 500 | Soft drop-shadow for legibility over photo |
| Section heading (H2) | Fraunces | `clamp(30px, 3.8vw, 46px)` | 500 | Generous line-height (1.08–1.1) |
| Eyebrow / Tag label | Manrope | 11px | 600 | `letter-spacing: .18em`, uppercase, gold-deep color, preceded by a short horizontal rule — this small detail is doing a lot of the "editorial luxury" work |
| Body copy | Manrope | 14–14.5px | 400 | `line-height: 1.6–1.7` — generous leading keeps paragraphs calm to read |
| Buttons | Manrope | 12.5–13px | 700 | `letter-spacing: .02em` |
| Chat/UI micro-labels | Manrope | 11.5px | 600 | `letter-spacing: .09em`, uppercase |

### 3.3 Why This Works for Luxury
- **Serif for emotion, sans for function** — a well-established luxury pattern (see most high-end fashion/jewelry sites). The customer reads headlines as "brand voice" and body/UI as "helpful assistant."
- **Wide letter-spacing on small caps labels** is the single most recognizable "editorial fashion magazine" typographic signal (Vogue Italia, fashion lookbooks) — cheap to implement, high perceived-value payoff.
- **Negative letter-spacing on headings** (`-0.01em`) tightens Fraunces slightly at large sizes so it doesn't feel loose or decorative.

### 3.4 Recommended Additions
- Add **Fraunces italic** (already loaded: `1,9..144,400`) for pull-quotes or testimonial text — currently underused, italics add editorial contrast without a new typeface.
- Define a documented **type scale (e.g. 12/14/16/20/28/38/46/64)** in the design file so future pages stay consistent instead of ad-hoc `clamp()` values per component.

---

## 4. UI Preferences

### 4.1 Shape Language
- **Buttons:** fully rounded (`border-radius: 40px`) — pill-shaped, soft, approachable, jewelry-adjacent (echoes a ring/bangle silhouette).
- **Cards, images, modals:** near-sharp corners (`border-radius: 2–8px`) — this contrast (soft buttons vs. crisp cards) is intentional: pills feel human/tactile, sharp edges feel precise/premium like a jewelry case.
- **Chat widget:** pill-shaped (`30px`), consistent with button language, not a circular bubble (circular = generic SaaS chat pattern).

### 4.2 Elevation / Shadow System
Shadows are used sparingly and always **soft, warm, and low-opacity** — never a hard drop shadow:
```
--shadow: 0 20px 45px -20px rgba(46,26,71,.35);   /* default card elevation */
Hover elevation:   0 30px 60px -20px rgba(0,0,0,.5)
Widget elevation:  0 14px 30px -14px rgba(0,0,0,.38)
```
Negative spread + high blur = a soft "floating" look rather than a boxed-in feel.

### 4.3 Motion & Animation (full inventory from the demo)

| Animation | Where | Duration / Easing | Purpose |
|---|---|---|---|
| Hero image crossfade | Hero background | 1.1s ease, cycles every 2s | Slideshow between product photography, no hard cuts |
| Parallax drift | Hero image, craft photo | Scroll-linked transform | Subtle depth, never more than ~15–20% translate |
| Scroll reveal | Nearly all sections | `.7s cubic-bezier(.22,.68,.3,1)`, translateY 24px → 0 | Content fades/rises in as the user scrolls — staggered with `.d1/.d2/.d3` delay classes (80ms/160ms/240ms) for sequential reveal |
| Card hover lift | Product cards | `.3s ease`, translateY(-6px) + shadow | Gentle lift, not a bounce or scale-jump |
| Image zoom on hover | Product card media, craft photo, Instagram grid | `.5s ease`, scale(1.06–1.08) | Slow, cinematic zoom — signals quality photography |
| Marquee ticker | Material/heritage claims strip | `26s linear infinite` | Slow, continuous — never feels like a "breaking news" ticker |
| Announcement bar rotation | Top bar | Fades every 4s, `.5s` opacity transition | Calm message rotation, no slide/bounce |
| Drawer slide-in | Cart | `transform: translateX()`, eased | Cart panel glides in from the right |
| Modal scale-in | Quick View | `.35s cubic-bezier(.22,.68,.3,1)`, scale(.95→1) + translateY | Soft pop, not a snap |
| Toast | Add-to-cart confirmation | Slides up + fades, auto-dismiss 2.6s | Non-blocking confirmation |
| Button press | All buttons | `transform: scale(.97)` on `:active` | Tiny tactile feedback, no color-flash |

**Global rule:** `prefers-reduced-motion` is respected site-wide — all animations collapse to `0.001ms` for accessibility. This should remain non-negotiable in production.

**Design principle behind all of the above:** nothing snaps, bounces, or spins. Every transition uses eased, elongated timing (`.3s` minimum, often `.5–.7s`) — this is the actual mechanism behind "luxury motion." Fast/bouncy easing reads as consumer-app; slow/eased easing reads as considered and expensive.

### 4.4 Iconography
- **Line icons only** (stroke-based SVG, 1.5–1.8px stroke width) — no filled/solid icons, no emoji anywhere in the interface.
- Icon color is either `gold-deep` (on light backgrounds) or `gold-light` (on dark backgrounds) — icons are never black/gray, keeping them tied to the brand palette even in a purely functional role (trust badges, chat, cart).

### 4.5 Layout & Spacing
- **Container:** `max-width: 1240px`, `padding: 0 32px` (18px on mobile) — generous outer margins on large screens, never edge-to-edge content.
- **Section rhythm:** `140px` vertical padding desktop / `88px` mobile — this generous whitespace is one of the top 3 highest-impact "this feels expensive" signals in the whole design.
- **Grid gaps:** consistently large (44–64px) between major layout columns — content is never cramped.

### 4.6 Card System — Full Inventory

This is every "card" component used in the demo — what it's for, its exact size, and its style. Kept consistent across all of them: **white/ivory fill, hairline border, near-sharp corners (2–14px depending on scale), slow eased hover (0.3–0.6s), never a hard shadow.**

| Card | Used for | Size / Aspect | Corner radius | Style notes |
|---|---|---|---|---|
| **Product Card** (`.card`) | Main shop grid | Grid: 3 cols desktop / 2 tablet / 1 mobile, `gap: 26px`. Media: `aspect-ratio 1:1` | `3px` | White fill, 1px hairline border. Hover: lifts `-6px` + soft shadow (`.3s`). Image zooms `1.08x` on hover (`.5s`). Top-left: 40×40px circular hallmark badge. Top-right: 34×34px circular wishlist button. Bottom: "Quick View" bar slides up on hover (hidden by default, `translateY(8px)→0`). Supports a 2-image dot-swipe stack (6px dots) for showing the piece from two angles. |
| **Carousel Card** (`.eg-card`) | "Più venduti" horizontal scroll-snap row | Fixed `220px` wide, media `aspect-ratio 1:1` | `4px` | Same white/border language, smaller footprint for a scannable horizontal row. 28×28px circular wishlist icon top-right. Compact body: name (13.5px Fraunces) + price (12px Manrope) side by side. |
| **Collection / Archive Card** (`.eg-arch-col`) | 3-across "shop by collection" editorial blocks | `460px` tall desktop / `360px` mobile, in a 3-col grid, `gap: 24px` | `14px` (largest radius on the site — deliberately, to signal "editorial/lifestyle" rather than "product/catalog") | Full-bleed photo with a dark gradient overlay (bottom-anchored) so a title sits directly on the image. `1.07x` slow zoom on hover (`.6s`). Soft drop shadow (`0 22px 44px`). |
| **Atelier CTA Card** (`.atelier-card`) | Embedded inside the product grid as a "visit us / book consultation" tile | `aspect-ratio 1:1.35` (taller than a product card, so it visually interrupts the grid rhythm intentionally) | `3px` | Solid emerald-deep fill (not white — the one card type that inverts to dark), centered icon + Fraunces heading + muted subtext. Darkens to `--ink` on hover. |
| **Testimonial Photo Card** (`.eg-testi-photo`) | Customer quote section, image half of the split layout | `aspect-ratio 4:5` | `8px` | Deepest shadow on the site (`0 30px 60px -20px`) since it sits on a dark emerald-deep section background and needs to visually lift off it. |
| **Instagram Grid Item** (`.eg-insta-item`) | Social proof strip, 4-across | `aspect-ratio 1:1`, 4-col grid, **no gap** (edge-to-edge) | `0px` (intentionally flush — this is the one deliberately "un-cardlike" grid, reads as a seamless gallery wall) | `1.08x` zoom on hover (`.45s`). One tile is a dark CTA overlay ("Follow us") instead of a photo. |
| **Process Step "Stamp"** (`.stamp`) | "How it works" step indicator | Circle, `92×92px` | `50%` (circle) | Default: white fill, 1.5px **dashed** border (unfinished/sketch feel). Hover/active: border becomes solid gold, fill becomes emerald-deep, icon turns gold-light and scales `1.08x`. This is the only dashed-border element on the site — used specifically to suggest "in progress / your journey" for a step indicator. |
| **Quick View Modal** (`.modal`) | Product preview overlay | `max-width: 880px`, `max-height: 88vh`, 2-col grid (image / details), stacks to 1-col under 700px | `4px` | Ivory fill, scale-in from `0.95→1` with slight `translateY` (`.35s`). 34×34px circular close button, top-right, offset outside the grid. |
| **Cart Drawer "Card"** (`.drawer`) | Slide-in cart panel | `420px` wide, `max-width: 92vw`, full viewport height | flush edge (no radius — it's a panel, not a floating card) | Ivory fill, slides in from the right (`translateX`, `.35s`). Each line item inside behaves like a mini horizontal card (thumbnail + name + qty + remove). |
| **Stat Block** (`.eg-stat`) | Hero-area trust numbers ("406 punti vendita" etc.) | No fixed size — text-only, centered, separated by a 1×44px hairline divider | n/a | Not a bordered card — deliberately "typographic only" so it doesn't compete visually with the hero photography behind it. |
| **Trust Strip Item** | Top-of-page reassurance row (shipping / returns / certification / secure payment) | Flex row item, icon (24×24px) + 2-line text | n/a | Also typographic/iconographic only, no card container — keeps this row feeling like a quiet header strip, not another product-style block. |

**Sizing logic across the system:** cards get *smaller radius* the more "catalog/functional" they are (product card `3px`, carousel `4px`) and *larger radius* the more "editorial/lifestyle" they are (collection card `14px`, testimonial photo `8px`). The Instagram grid intentionally breaks the pattern with `0px` to read as a continuous gallery rather than a set of cards. This radius gradient is a deliberate, repeatable rule — worth keeping as new card types are added.

### 4.6.1 Product Card — Double-Image Hover Detail
The Product Card is the one component with real interactive logic behind it, so it's worth documenting separately.

**Behavior:**
- Each product can optionally have two images: a primary shot (`img`) and an alternate (`img2`) — e.g. worn-on-hand vs. studio detail shot, or front vs. side angle.
- **Desktop (hover-capable):** on mouse-enter, the card cross-fades from `img` → `img2` (`.4s ease`, opacity swap via `.ci.active` class); on mouse-leave, it reverts to `img`.
- **Touch/mobile (no hover):** two small dot indicators (`6px`, `.cdot`) sit at the bottom-center of the image, so the customer can tap to manually switch between the two photos — this is the accessible fallback for the hover interaction.
- **Graceful degradation:** if a product only has one image (`img2` is empty/undefined), neither the second image nor the dots render at all — the card silently behaves as a single-image card. No placeholder, no broken state.

**Why it matters for luxury perception:** a hover-reveal detail shot mimics the in-store experience of a sales associate turning a piece over in their hand to show a different facet — it rewards attention rather than demanding an extra click, which is the same principle behind Net-a-Porter/Mytheresa-style product cards.

**Image guideline for this pattern (for whoever shoots/sources product photography):**

| | Primary image (`img`) | Alternate image (`img2`) |
|---|---|---|
| Purpose | The "identifying" shot — clean, centered, on white/neutral or on-model | The "story" shot — different angle, macro detail, or worn context |
| Crop | Square (1:1), subject centered with even margin | Same square crop/framing as primary, so the swap doesn't jump or resize |
| Lighting | Consistent studio lighting used across the whole catalog (see §1.7 photography note) | Same lighting setup as primary — the two images should read as one continuous shoot, not two different sessions |
| File weight | Optimize both to the same target size (e.g. WebP, <150KB) since both load for every product card that has a second image | Same |

### 4.7 Components to Add for Production Completeness
- **Skeleton loaders** (see §1.6) — styled as soft ivory/line-colored pulsing blocks matching card shapes, not generic gray boxes.
- **Loading state for images** — low-quality-image-placeholder (LQIP) blur-up as real photos load, so the crossfade/zoom effects don't reveal a flash of unstyled content.
- **Focus states** — visible, on-brand focus rings (currently relies on browser default) for keyboard navigation — required for accessibility and still achievable in a way that matches the gold/emerald palette.
- **404 / error page** — styled in the same voice (Fraunces headline + a single elegant CTA back to the homepage), not a default framework error page.
- **Newsletter/signup component** — currently absent; a quiet, single-field email capture in the footer (no popup) fits the site's restrained tone better than a modal.

---

## Summary — The 5 Mechanisms That Make This Feel Luxury
1. **Slow, eased motion everywhere** (0.3–0.7s, no bounce, no snap)
2. **Generous whitespace** (140px section padding, wide gaps)
3. **Restricted jewel-tone palette, ratio-based restraint** (lavender-ivory field carrying violet/sapphire/citrine accents — saturation stays in small accent moments, never used for discount/sale signaling)
4. **Serif + wide-tracked uppercase labels** (the Fraunces/Manrope pairing + `.18em` letter-spacing)
5. **Absence of urgency mechanics** (no countdowns, no gamified counters, no aggressive popups — quiet confidence instead)

Production work still needed: skeleton loaders, empty states, size guide, error/404 page, and a real, consistent photoshoot to replace the current stock imagery.
