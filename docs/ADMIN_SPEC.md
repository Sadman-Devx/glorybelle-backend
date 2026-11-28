# GLORYBELLE Admin API — Audit and Proposal

## Scope and evidence

This audit describes `Sadman-Devx/glorybelle-backend` on `main` at
[`8b2aa3ae597af1263b04ee386c312ca71c57ad0a`](https://github.com/Sadman-Devx/glorybelle-backend/commit/8b2aa3ae597af1263b04ee386c312ca71c57ad0a).
The backend is a separate repository from this frontend checkout. “Current” below
means behavior visible in that snapshot; the admin API section is a proposal, not
an implemented contract.

## 1. Backend inventory

### Models

| Model | Fields and behavior |
|---|---|
| `Order` | `id`, unique `order_number`, unique `idempotency_key`; nullable `user` (`SET_NULL`); `email`; `status`; snapshotted shipping and billing names, address lines, city, province, postal code, and country; `subtotal`, `discount_percent`, `discount_amount`, `shipping_cost`, `total`; `stripe_payment_intent_id`; customer `notes`; `created_at`, `updated_at`. It allows guest checkout. |
| `OrderItem` | `id`, `order` (`CASCADE`), `variant` (`PROTECT`); purchase-time snapshots `product_name`, `variant_metal`, `variant_metal_display`, `variant_size`, `sku`, `unit_price`, `quantity`, `line_total`. |
| `Category` | `id`, `name`, unique `slug`, optional `description`, optional `image`, nullable self-parent (`SET_NULL`), `is_active`, `sort_order`, `created_at`, `updated_at`. |
| `Product` | `id`, protected `category`, `name`, unique `slug`, optional `description`, `base_price`, `metal`, `gem`, `purity`, `is_active`, `is_featured`, `created_at`, `updated_at`. |
| `ProductVariant` | `id`, `product` (`CASCADE`), `metal`, `size`, unique `sku`, optional `price_override`, `stock_quantity`, `reserved_quantity`, `is_active`, `created_at`, `updated_at`; unique per product/metal/size. Resolved price is the override or product base price; available stock subtracts reservations. |
| `ProductImage` | `id`, `product` (`CASCADE`), required `image`, optional `image_alt`, `alt_text`, `is_primary`, `sort_order`, `created_at`. Product images are the current media model; category images are stored directly on `Category`. |
| `User` | Django’s built-in `django.contrib.auth.models.User`, not a custom user model. Standard fields include username, password hash, first/last name, email, `is_staff`, `is_active`, `is_superuser`, last login, and date joined. There is no Manager/Viewer role model. |
| `CustomerProfile` | One-to-one user; `phone`, optional `date_of_birth`, `created_at`, `updated_at`. |
| `Address` | User; `first_name`, `last_name`, `line1`, optional `line2`, `city`, `province`, `postal_code`, `country`, `is_default`, `created_at`, `updated_at`. |
| `Payment` | One-to-one order; unique Stripe PaymentIntent ID; optional charge ID; `amount`, `currency`, `status`, unique idempotency key, timestamps. |
| `ProcessedWebhookEvent` | Unique Stripe event ID, event type, processing timestamp; used for webhook idempotency. |
| Other domain models | `Cart`, `CartItem`, `StockReservation`, `Invoice`, `Review`, `Wishlist`, `WishlistItem`, and `NewsletterSubscriber`. Newsletter consent uses `is_active`, `is_confirmed`, and `unsubscribed_at`; reviews have `is_approved`. |

There is **no `Enquiry` model** in the installed app list or API routes.

### Serializers

- **Orders:** `CheckoutSerializer` validates checkout input; `OrderSerializer`
  returns full order detail and read-only line items; `OrderListSerializer`
  returns order history summaries; `OrderItemSerializer` exposes snapshotted line
  item data. The order serializers are read-only.
- **Catalog:** `CategorySerializer`, `ProductImageSerializer`,
  `ProductVariantSerializer`, `ProductListSerializer`, and
  `ProductDetailSerializer`. Current public catalog serializers are read-only.
- **Accounts:** `RegisterSerializer`, `CustomerProfileSerializer`,
  `AddressSerializer`, password-reset serializers, and
  `FirstPurchaseDiscountSerializer`.
- **Cart:** `CartSerializer`, `CartItemSerializer`, `AddToCartSerializer`, and
  `UpdateCartItemSerializer`.
- **Other:** `ReviewSerializer` / `ReviewCreateSerializer`,
  `WishlistItemSerializer` / `WishlistToggleSerializer`, and newsletter
  subscribe/unsubscribe serializers. Payments have no DRF serializer for the
  checkout response or webhook.

### Existing API routes and permissions

DRF uses page-number pagination globally (`page_size=8`, configurable up to
100), django-filter, search, and ordering backends. These are **customer-facing
routes**, not an admin API.

| Methods and paths | Current behavior / permission |
|---|---|
| `GET /api/categories/`, `GET /api/categories/{slug}/` | Active categories; public (`AllowAny`). |
| `GET /api/products/`, `GET /api/products/featured/`, `GET /api/products/{slug}/`, `GET /api/search/` | Active products, filters/search and pagination; public (`AllowAny`). |
| `POST /api/accounts/register/`, `POST /api/accounts/login/`, `POST /api/accounts/token/refresh/` | Registration and SimpleJWT token issue/refresh; public. |
| `POST /api/accounts/logout/` | Refresh-token blacklist; authenticated. |
| `POST /api/accounts/password/reset/`, `POST /api/accounts/password/reset/confirm/` | Password reset; public. |
| `GET` / `PATCH /api/accounts/me/` | Current customer profile; authenticated. |
| `GET`, `POST`, `GET/PATCH/PUT/DELETE /api/accounts/addresses/{id}/` | Customer-owned addresses; authenticated and owner-scoped. |
| `GET /api/accounts/first-purchase-discount/` | Eligibility information; public. |
| `GET` / `DELETE /api/cart/`, `POST /api/cart/items/`, `PATCH` / `DELETE /api/cart/items/{id}/`, `POST /api/cart/merge/` | Guest or customer cart; public (`AllowAny`), cart is scoped using user or Django session. |
| `POST /api/checkout/` | Creates an order and Stripe PaymentIntent; public/guest checkout (`AllowAny`). Details below. |
| `GET /api/orders/`, `GET /api/orders/{order_number}/` | Authenticated customer’s own order list/detail; `IsAuthenticated`, owner-scoped. |
| `POST /api/webhooks/stripe/` | Stripe webhook; no DRF auth, signature-verified. |
| `GET /api/products/{slug}/reviews/`, `POST /api/products/{slug}/reviews/create/` | Public approved reviews; authenticated review submission, pending moderation. |
| `GET /api/wishlist/`, `POST /api/wishlist/toggle/`, `DELETE /api/wishlist/items/{product_id}/` | Authenticated customer’s wishlist. |
| `POST /api/newsletter/subscribe/`, `POST /api/newsletter/confirm/`, `POST /api/newsletter/unsubscribe/` | Public newsletter operations; subscription requires a signed email confirmation. |
| `GET /api/schema/`, `GET /api/docs/`, `GET /api/redoc/` | OpenAPI schema and documentation. |

There are no `/api/admin/` routes. The default DRF permission is
`IsAuthenticatedOrReadOnly`; public catalog viewsets explicitly use `AllowAny`
and are read-only. A custom `IsAdminOrReadOnly` helper checks `user.is_staff`,
but code search finds no use of that helper on the catalog viewsets or elsewhere.
The normal Django admin remains registered at `/admin/` and uses Django’s
standard staff/superuser access checks. Order status and deletion are disabled
in its `OrderAdmin`; it does not provide a cancel/archive action.

### Order statuses and transitions currently present

`Order.STATUS_CHOICES` are `pending` (default), `paid`, `processing`, `shipped`,
`delivered`, `cancelled`, and `refunded`.

The code currently creates orders as `pending`. The signed Stripe
`payment_intent.succeeded` webhook sets the order to `paid`; the
`payment_intent.payment_failed` webhook sets it to `cancelled`. No application
transition service/API for `processing`, `shipped`, `delivered`, or `refunded`
was found. The Django admin marks `status` read-only. Choices define allowed
values, not a transition state machine.

## 2. Authentication, CORS, and CSRF

- **Library:** `djangorestframework-simplejwt` (Django 5.1.15 and DRF 3.15.x
  range in requirements).
- **Lifetimes:** access 30 minutes; refresh 7 days. Refresh tokens rotate and
  the old refresh token is blacklisted.
- **API transport:** SimpleJWT accepts the `Authorization: Bearer <access>`
  header. The frontend stores customer tokens in `localStorage` and
  `src/lib/api.ts` sends the access token in that header. It also sets
  `credentials: "include"`, but the access/refresh tokens are not issued as
  cookies by these backend views.
- **Other authentication:** DRF also enables `SessionAuthentication`. Base
  settings use Redis-backed Django sessions; local settings switch to DB-backed
  sessions. Unsafe requests authenticated by `SessionAuthentication` require
  CSRF validation. Django’s `CsrfViewMiddleware` is enabled. The Stripe webhook
  is explicitly CSRF-exempt and verifies Stripe’s signature instead.
- **CORS:** `django-cors-headers`; base config allows the comma-separated
  `CORS_ALLOWED_ORIGINS` setting (default `http://localhost:3000`) and enables
  credentials. Local settings allow localhost ports 3000 on `localhost` and
  `127.0.0.1`. Production relies on the configured origin list.
- **CSRF trusted origins:** no `CSRF_TRUSTED_ORIGINS` setting was found in the
  reviewed settings. Production enables secure session and CSRF cookies,
  HTTPS redirect, and HSTS.
- **`is_staff`:** the only explicit API-side check is inside the unused
  `IsAdminOrReadOnly` helper. It is not a Manager/Viewer implementation.
  Django’s built-in `/admin/` independently uses the normal `is_staff` check.
  No custom user roles or role-specific API permissions exist.

### Proposed admin authentication

| Option | Pros | Cons |
|---|---|---|
| **(i) Next.js route handlers as a BFF**; browser uses a same-origin `HttpOnly` cookie, Next proxies to Django and supplies the backend bearer token server-side. | Keeps JWTs out of browser storage and JavaScript; avoids browser-to-Django CORS; consistent when frontend and API are on separate domains; a narrow proxy can enforce CSRF/origin checks and expose only admin routes. | Requires a server-side session/token store or careful encrypted cookie lifecycle, refresh rotation, logout/revocation, and proxy hardening; adds a network hop and deployment work. |
| **(ii) Browser calls Django directly using cookies** | Fewer proxy components; Django remains the direct API boundary. | Requires a cookie-auth implementation (SimpleJWT does not currently set these cookies), strict CSRF token handling on every unsafe request, credentialed CORS, and origin configuration. Separate registrable domains require `SameSite=None; Secure` and may be affected by third-party-cookie restrictions; same-site subdomains still require CORS and CSRF configuration. |

**Recommendation: option (i), BFF with server-side admin sessions.** Use an
opaque `Secure`, `HttpOnly`, `SameSite=Lax` cookie scoped to the frontend host;
keep Django access/refresh credentials in a server-side session store; have
Next.js route handlers proxy allowlisted `/api/admin/` requests over TLS and
attach the `Authorization: Bearer` header. Protect cookie-authenticated BFF
mutations with Origin checks and a CSRF token. Browser traffic then stays
same-origin and does not need Django CORS; server-to-server traffic is not
governed by browser CORS. If deployments cannot support the BFF, direct calls
need explicit cookie issuance, CSRF, CORS, and separate-domain browser testing
before adoption.

## 3. Payments and paid-state source of truth

`POST /api/checkout/` gets the current cart, creates a pending order, then uses
the Stripe SDK to create a EUR PaymentIntent for `order.total` in cents. The
PaymentIntent idempotency key is deterministic per order number. A `Payment`
record is created with `status="pending"`.

Stripe sends `POST /api/webhooks/stripe/`. The endpoint verifies
`Stripe-Signature`, rejects invalid signatures, and dispatches
`payment_intent.succeeded` or `payment_intent.payment_failed`. A
`ProcessedWebhookEvent` row prevents replay processing. Success updates
`Payment.status` to `succeeded` and `Order.status` to `paid`; failure updates
the payment to `failed` and order to `cancelled`.

**Canonical application field:** `Order.status == "paid"` is the field customer
order views use to determine paid status. The verified Stripe webhook is the
authority that changes it; `Payment.status` records the related payment
lifecycle. A client-side redirect or Stripe.js result is not the backend
source of truth.

## 4. Media storage and serving

`ProductImage.image`, `ProductImage.image_alt`, and `Category.image` are Django
`ImageField`s. Base settings configure `django-cloudinary-storage` as the
default file storage, with Cloudinary credentials from environment settings;
the local settings override storage to Django `FileSystemStorage`. `MEDIA_ROOT`
is `<BASE_DIR>/media` and `MEDIA_URL` is `media/`. Serializers return image
URLs using the storage backend’s `.url` and `request.build_absolute_uri()`.
Product images can be uploaded through inline Django admin fields; there is no
dedicated upload API.

The reviewed URL configuration does not add a Django `static()` route for
media. In production Cloudinary provides the hosted image URLs when configured;
local deployments need a web server or explicit development media-serving
configuration for `/media/` URLs.

## 5. Checkout request discrepancy and exact current contract

### Route mismatch

The backend exposes **`POST /api/checkout/`**, not `POST /api/orders/`.
`/api/orders/` is `GET`-only order history. The checked-in frontend helper
currently calls `/api/orders/create/` and types the response as a bare `Order`;
that path and response expectation do not match this backend snapshot.

### Which nested shipping-address shape is accepted?

`CheckoutSerializer` accepts a generic `shipping_address` dictionary, then
explicitly requires these keys:

```json
{
  "first_name": "...",
  "last_name": "...",
  "line1": "...",
  "city": "...",
  "province": "...",
  "postal_code": "..."
}
```

Therefore `{first_name,last_name,line1,...}` is the accepted frontend shape.
The alternative `{recipient_name,street_address,...}` is rejected because it
does not supply the six required keys. `phone` is not a persisted order field
and is not consumed by order creation.

### Exact request fields

Required at the top level:

- `email`: required email address.
- Either `shipping_address_id` or `shipping_address`.
- When `shipping_address` is supplied, its required keys are
  `first_name`, `last_name`, `line1`, `city`, `province`, and `postal_code`.

Optional:

- `notes`: optional string; defaults to `""`.
- `idempotency_key`: optional UUID.
- `shipping_address_id`: optional integer referencing the authenticated
  customer’s saved address. Guest requests must supply `shipping_address`.
- `shipping_address`: optional dictionary. `line2` is optional and defaults to
  empty; `country` is optional and defaults to `"IT"`. The validator does not
  reject extra keys or validate nested field types.
- `billing_same_as_shipping`: optional boolean, default `true`.
- `billing_address_id`: optional integer; requires an authenticated user when
  used. If `billing_same_as_shipping` is true, the shipping address is used.
- `billing_address`: optional dictionary. When used with
  `billing_same_as_shipping=false`, order creation reads
  `first_name`, `last_name`, `line1`, `city`, `province`, and `postal_code`;
  `line2` and `country` default to empty and `"IT"`. The serializer does not
  perform equivalent nested billing validation.

The cart, variant prices, discount, shipping cost, and total are resolved by
the backend; clients do not submit prices or line items.

### Response from `POST /api/checkout/`

Success is an envelope, not a bare order:

```json
{
  "order": {
    "id": 123,
    "order_number": "GB-YYYYMMDD-XXXX",
    "idempotency_key": "uuid",
    "email": "cliente@example.it",
    "status": "pending",
    "status_display": "In attesa di pagamento",
    "shipping_first_name": "...",
    "shipping_last_name": "...",
    "shipping_line1": "...",
    "shipping_line2": "",
    "shipping_city": "...",
    "shipping_province": "...",
    "shipping_postal_code": "...",
    "shipping_country": "IT",
    "billing_first_name": "...",
    "billing_last_name": "...",
    "billing_line1": "...",
    "billing_line2": "",
    "billing_city": "...",
    "billing_province": "...",
    "billing_postal_code": "...",
    "billing_country": "IT",
    "subtotal": "100.00",
    "discount_percent": "0.00",
    "discount_amount": "0.00",
    "has_discount": false,
    "shipping_cost": "0.00",
    "total": "100.00",
    "notes": "",
    "items": [
      {
        "id": 1,
        "product_name": "...",
        "variant_metal": "gold",
        "variant_metal_display": "...",
        "variant_size": "52",
        "sku": "...",
        "unit_price": "100.00",
        "quantity": 1,
        "line_total": "100.00"
      }
    ],
    "created_at": "...",
    "updated_at": "..."
  },
  "client_secret": "...",
  "payment_intent_id": "pi_..."
}
```

The order’s detailed fields above are the `OrderSerializer` fields. On an
idempotent retry the backend returns HTTP 200 and additionally
`"idempotent_replay": true`; a newly created checkout returns HTTP 201.

## 6. Proposed `/api/admin/` API

### Authorization and shared contracts

Every `/api/admin/` handler must enforce authorization server-side; frontend
visibility is not an access control. Require authenticated staff for the admin
namespace, then authorize roles/objects:

| Actor | Orders | Products, categories, media | Enquiries | Users and roles |
|---|---|---|---|---|
| Superuser | Read/write | Read/write | Read/write | Read/write |
| Manager | Read/write | Read/write | Read/write | No access |
| Viewer | Read-only | Read-only | Read-only | No access |
| Authenticated customer without an admin role | `403` | `403` | `403` | `403` |
| Anonymous | `401` | `401` | `401` | `401` |

Implement explicit DRF permissions for each resource/action and verify role
membership on the server. Django superusers retain the built-in `/admin/`
fallback. Suggested response conventions: all lists use
`{count,next,previous,results}` with page/page_size (maximum 100), search,
filters, and ordering; detail and successful writes return the resource JSON.
Use `400` for invalid input, `404` for missing records, and `409` for invalid
state transitions or conflicting updates. No hard-delete method is proposed
for orders or products.

### Proposed endpoints

`M` = Manager or superuser; `V` = Viewer (GET only); `S` = superuser only.
Every route below is under `/api/admin/`.

| Method and path | Permission | Request | Response |
|---|---|---|---|
| `GET /dashboard/` | M, V, S | None. | Today's order count, successful-payment revenue over the last 7/30 days, counts by status, and active variants with stock ≤ 3. Cached for 60 seconds. |
| `GET /orders/` | M, V, S | Query: `page`, `page_size`, `search`, `status`, `created_after`, `created_before` (ISO-8601), `email`, `order_number`, `total_min`, `total_max`, `ordering`, `include_archived`. | Paginated compact summaries: ID/number, date, customer, total, status, item count. Archived orders are hidden unless explicitly included. |
| `GET /orders/{id}/` | M, V, S | None. | Order, line items, shipping/billing address snapshots, payment/refund summary, status history, internal notes, and archive metadata. |
| `POST /orders/{id}/transition/` | M, S | `{ "status": "processing|shipped|delivered", "tracking_number": "..." }` (tracking number optional and only accepted for `shipped`). | Updated order and history. `pending → paid` is never an admin transition; only the verified Stripe webhook sets `paid`. |
| `POST /orders/{id}/cancel/` | M, S | `{ "reason": "..." }` (required). | `{ "order": ..., "audit_event": ... }`; preserve the row/items, record actor/reason, and request a full Stripe refund for a verified successful payment. |
| `POST /orders/{id}/archive/` | M, S | `{ "reason": "..." }` (required). | `{ "order": ..., "audit_event": ... }`; set archive metadata without deleting or rewriting payment history. |
| `GET /orders/{id}/history/` | M, V, S | Pagination, `search`, `history_type`, `history_user_id`, `history_date__gte`, `history_date__lte`, `ordering`. | Paginated immutable status/history records for the order. |
| `GET /orders/{id}/notes/` | M, V, S | Pagination, `search`, `author_id`, `created_at__gte`, `created_at__lte`, `ordering`. | Paginated internal-only notes, never included in customer order responses. |
| `POST /orders/{id}/notes/` | M, S | `{ "body": "..." }` (required). | Created staff note with author and timestamp. |
| `GET /products/` | M, V, S | Query: pagination, `search` (name/slug/SKU), `category`, `is_active`, `is_featured`, `ordering`. | Paginated products with primary media and variant counts. |
| `POST /products/` | M, S | Product fields: `name`, `slug`, `category`, `description`, `base_price`, `metal`, `gem`, `purity`, flags; optional `variants` array. Prices and stock are validated server-side. | Created product with variants; record audit event. |
| `GET /products/{id}/` | M, V, S | None. | Product, variants, and image metadata. |
| `PATCH /products/{id}/` | M, S | Partial allowlisted editable product fields. | Updated product plus audit event; do not allow client to write computed values. |
| `POST /products/{id}/archive/` | M, S | `{ "reason": "..." }`. | Product with `is_active=false` and audit event; retain historical variant references. |
| `GET /products/{id}/variants/` | M, V, S | Pagination/search/filter by `metal`, `size`, `is_active`. | Paginated variants including stock, reserved, and available counts. |
| `POST /products/{id}/variants/` | M, S | `metal`, `size`, `sku`, optional `price_override`, `stock_quantity`, `is_active`. | Created variant and audit event. |
| `PATCH /products/{id}/variants/{variant_id}/` | M, S | Partial variant fields. Stock changes must use a transaction and a locked row. | Updated variant and audit event. Do not delete a variant referenced by an order. |
| `GET /categories/` | M, V, S | Pagination, `search`, `is_active`. | Paginated categories. |
| `POST /categories/` | M, S | `name`, `slug`, optional `description`, `parent`, `image`, `sort_order`, `is_active`. | Created category and audit event. |
| `PATCH /categories/{id}/` | M, S | Partial allowlisted category fields. | Updated category and audit event. |
| `POST /categories/{id}/archive/` | M, S | `{ "reason": "..." }`. | Category with `is_active=false` and audit event. |
| `GET /media/` | M, V, S | Pagination, `product`, `category`, `search`, `is_primary`. | Paginated media metadata and URLs. |
| `POST /media/` | M, S | `multipart/form-data`: `product_id` or `category_id`, `image`; optional `image_alt`, `alt_text`, `is_primary`, `sort_order`. | Created media record and URLs; validate MIME/type/size and record actor/event. |
| `PATCH /media/{id}/` | M, S | `alt_text`, `is_primary`, `sort_order`, and any supported image replacement. | Updated media metadata and audit event. |
| `DELETE /media/{id}/` | M, S | None. | `204`; remove the relationship and delete the stored object only when unreferenced. Record the operation. |
| `GET /enquiries/` | M, V, S | Pagination, `search` (name/email/subject), `status`, date filters. | Paginated enquiry summaries. |
| `GET /enquiries/{id}/` | M, V, S | None. | Full enquiry and status/history. |
| `PATCH /enquiries/{id}/` | M, S | `{ "status": "new|read|replied|closed", "internal_note": "..." }`. | Updated enquiry and audit event; retain customer message unchanged. |
| `POST /enquiries/{id}/archive/` | M, S | `{ "reason": "..." }`. | Archived enquiry and audit event; do not erase its content. |
| `GET /audit-events/` | M, V, S | Pagination, `actor`, `resource_type`, `resource_id`, date filters. | Paginated events with actor, timestamp, action, resource, reason, and changed-field summary. |
| `GET /audit-events/{id}/` | M, V, S | None. | Immutable event with before/after values, redacted for secrets and unnecessary personal data. |
| `GET /users/` | S | Pagination and `search` (username/email), `is_active`, role filter. | Paginated user summaries and assigned admin groups; never expose password/token fields. |
| `POST /users/invitations/` | S | `{ "email": "...", "role": "manager|viewer" }`. | Invitation/created account state; send a one-time setup link, never accept or return a raw password. |
| `GET /users/{id}/` | S | None. | User profile, `is_active`, role/group assignments. |
| `PATCH /users/{id}/` | S | `{ "is_active": true, "roles": ["manager"] }` (allowlisted fields). | Updated safe user representation. Prevent demoting or disabling the last active superuser. |

The proposed product/category `archive` actions use the existing `is_active`
flags; adding `archived_at` and an archive reason is preferable if the UI must
distinguish archived content from intentionally inactive inventory. Order
cancellation and archival reasons belong in audit/history data, not customer
notes. Do not offer `DELETE /orders/{id}/`.

For customer-submitted enquiries, add a separate public
`POST /api/enquiries/` intake endpoint only after agreeing on form fields and
spam controls. It should create an enquiry and return a minimal receipt, never
expose internal notes or other enquiries.

### Orders API transition and dashboard contract

The order state machine is explicit: `paid → processing`, `paid → shipped`,
`processing → shipped`, and `shipped → delivered`. No admin action can set
`paid`; the signed Stripe webhook remains the source of truth. Cancellation
requires a reason and is limited to `pending`, `paid`, and `processing`; a
successful Stripe payment must be refunded in full before the order is marked
cancelled. Refund requests use a stable Stripe idempotency key and validate the
payment currency, intent, and amount against the order. Shipped and delivered
orders cannot be cancelled through this endpoint.

Archival is independent of order status and does not delete or alter payment
records. The default order list excludes archived rows; `include_archived=true`
includes them. Status transitions, cancellation, and archival are recorded by
order history with the acting user, timestamp, and change reason. Internal
notes use a separate staff-only record and are not serialized by customer APIs.

Dashboard revenue is the sum of successful EUR payment records created during
the preceding rolling 7- and 30-day windows; refunded payments are excluded.
The low-stock widget includes active variants whose `stock_quantity` is at most
three. Its aggregate response is cached for 60 seconds.

## 7. Gaps and implementation requirements

- **Enquiries:** no model or route exists. Define the contact fields, consent/
  retention policy, statuses, and spam/rate-limit approach before implementation.
- **Soft delete/archive:** there is no unified archive model or reason trail.
  Product/category/variant `is_active` and newsletter `is_active` are status
  flags, not a general archive mechanism. Orders have no archive fields or
  admin/API action. The order Django admin prevents hard deletion, but that is
  not a substitute for auditable cancellation/archive.
- **Change history:** there is no domain audit/history model. Django’s built-in
  admin log is not a complete field-level audit for API/admin operations.
  Add immutable audit events for every order/product/variant/category/media
  mutation, recording actor, timestamp, action, changed fields, and a
  required reason for cancellation/archive. Capture API and Django-admin
  changes consistently.
- **Uploads:** no dedicated API upload strategy exists. Current product images
  are uploaded via Django admin to Cloudinary when configured, while local
  settings use the filesystem. The admin API should validate files, use a
  private server-side Cloudinary configuration or equivalent object storage,
  return stable URLs, and avoid exposing storage credentials to the browser.
- **Role enforcement:** add Manager and Viewer role assignments (Django groups
  are a suitable minimal implementation), a server-side permission class for
  every admin endpoint, object-level scoping, and endpoint tests for anonymous
  `401`, customer `403`, allowed staff `200`, and wrong-role `403`. Do not
  equate every `is_staff` user with a Manager.
- **Status lifecycle:** define and validate transitions before enabling staff
  order actions. Preserve verified webhook authority over paid state; do not
  let a generic admin patch mark an order paid.
- **Pagination/search:** apply pagination, filters, and search to every new
  admin list route, even where current customer APIs do not expose all of
  these.
- **Frontend exposure:** admin pages should be `noindex` and excluded from
  sitemap and robots allow-lists; no backend secrets or service credentials
  belong in frontend environment variables.

## Open questions

1. Should order archival hide an order only from routine views, or should it also
   change a customer-visible status? What retention period applies?
2. Which order transitions should Managers be allowed to make, and which actions
   require a reason (for example cancellation, refund, or reopening)?
3. What fields must a customer enquiry contain, and should Managers be allowed
   to send replies from the admin UI or only record reply status?
4. Should Viewers be able to see customer email/address details and audit-event
   before/after values, or should those fields be masked?
5. Should Manager/Viewer accounts be created by invitation only, and who may
   assign or revoke those roles?
6. Is Cloudinary the required production upload store, and what image size/type
   limits and deletion/retention policy should apply?
7. Should the admin BFF use Django-issued JWTs stored in a server-side session,
   or should the backend introduce a dedicated Django session-based admin
   authentication flow?
8. Which production frontend/API origins should be allowed, and are they on the
   same site or separate registrable domains?
