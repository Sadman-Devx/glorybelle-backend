# First Purchase Discount Feature — GLORYBELLE

Adds a 10% first-purchase discount for newly registered customers + birth_date field at registration.

## ⚠️ Positioning Note (per rule.md §5)

PRD §1.2 explicitly pivoted AWAY from mass-retail discount tactics (countdowns,
giveaways, "X left in stock!", installment badges). However, a **first-purchase
discount** is a different category — it's an acquisition incentive, not an urgency
mechanic. Luxury retailers (Net-a-Porter, Mytheresa, SSENSE) all use it.

The implementation follows the boutique tone:
- NO popup, NO full-screen modal
- Quiet inline banner in cart drawer + register page
- Auto-applied at checkout (no coupon code to enter)
- Visible in order summary as a discount line

## Files Modified (Backend — 8)

| File | Change |
|---|---|
| `config/settings/base.py` | Add `FIRST_PURCHASE_DISCOUNT_PERCENT = 10.00` + `FIRST_PURCHASE_DISCOUNT_MIN_SUBTOTAL` |
| `apps/orders/models.py` | Add `discount_percent` + `discount_amount` fields to Order |
| `apps/orders/migrations/0003_order_discount_fields.py` | New migration |
| `apps/orders/services.py` | Add `is_first_purchase()` + `calculate_discount()` + apply in `create_order_from_cart()` |
| `apps/orders/serializers.py` | Expose `discount_percent`, `discount_amount`, `has_discount` in OrderSerializer + OrderListSerializer |
| `apps/accounts/serializers.py` | Add `birth_date` field to RegisterSerializer + FirstPurchaseDiscountSerializer |
| `apps/accounts/views.py` | Add `FirstPurchaseDiscountView` (GET /api/accounts/first-purchase-discount/) |
| `apps/accounts/urls.py` | Register the new endpoint |

## Files Modified (Frontend — 5)

| File | Change |
|---|---|
| `src/lib/api.ts` | Add `auth.firstPurchaseDiscount()` method |
| `src/lib/types.ts` | Add `FirstPurchaseDiscount` type |
| `src/app/register/page.tsx` | Add `birth_date` field + discount banner at top |
| `src/app/register/page.module.css` | Style for discount banner + birth_date input |
| `src/components/cart/FirstPurchaseBanner.tsx` + `.module.css` | NEW — inline banner in cart drawer |

## Installation Steps

### Backend

1. Copy files into your `glorybelle-backend` repo
2. Add the snippet from `config/settings/discount_settings_snippet.py` to the END of your existing `config/settings/base.py` (before the UNFOLD section)
3. Run migration:

   ```bash
   python manage.py migrate orders 0003_order_discount_fields
   ```

4. Restart Django dev server

### Frontend

1. Copy files into your `glorybelle-frontend` repo
2. Update `src/lib/api.ts` — replace the existing `auth` object with the one from `src/lib/api_extension.ts`
3. Update `src/lib/types.ts` — add the `FirstPurchaseDiscount` interface:

   ```ts
   export interface FirstPurchaseDiscount {
     eligible: boolean;
     percent: string;
     message: string;
   }
   ```

4. Update `src/app/register/page.tsx` — replace with the new version (has birth_date field)
5. Update `src/app/register/page.module.css` — replace with the new version (has discount banner styles)
6. Add `src/components/cart/FirstPurchaseBanner.tsx` + `.module.css`
7. Update `src/components/cart/CartDrawer.tsx` — import and render `<FirstPurchaseBanner />` above the cart items list

## How It Works

### Eligibility

A user is eligible for the 10% discount if:
- They are authenticated (registered)
- They have NO prior orders with status `paid`, `processing`, `shipped`, or `delivered`

Cancelled/pending/refunded orders don't count (they didn't complete a purchase).

### Discount Calculation

```
subtotal = sum(item.unit_price × item.quantity)
discount_amount = subtotal × (FIRST_PURCHASE_DISCOUNT_PERCENT / 100)
total = subtotal - discount_amount + shipping_cost
```

Applied automatically in `apps/orders/services.py:create_order_from_cart()` — no coupon code required.

### Frontend Flow

1. Guest browses products, adds to cart
2. Cart drawer shows `<FirstPurchaseBanner />` above items:
   - "10% di sconto sul primo ordine — Registrati ora"
3. Guest clicks "Registrati" → goes to /register
4. Register form requires birth_date (must be 13+ years old)
5. After register → auto-login → returns to cart
6. Cart drawer now shows: "Hai diritto al 10% di sconto"
7. At checkout → 10% automatically applied → visible in order summary

## API Endpoint

```http
GET /api/accounts/first-purchase-discount/
```

- **Auth:** AllowAny (works for guests + authenticated users)
- **Response:**

  For guest:
  ```json
  {
    "eligible": true,
    "percent": "10.00",
    "message": "Registra un account e ottieni il 10% di sconto sul primo ordine."
  }
  ```

  For authenticated first-time buyer:
  ```json
  {
    "eligible": true,
    "percent": "10.00",
    "message": "Hai diritto al 10% di sconto sul tuo primo ordine!"
  }
  ```

  For returning customer:
  ```json
  {
    "eligible": false,
    "percent": "10.00",
    "message": ""
  }
  ```

## Verification

1. **Backend test** (Python shell):
   ```python
   from apps.orders.services import is_first_purchase, calculate_discount
   from decimal import Decimal
   from django.contrib.auth.models import User

   user = User.objects.first()  # any user
   print(is_first_purchase(user))  # True if no prior orders
   print(calculate_discount(Decimal('100.00'), user))  # (Decimal('10.00'), Decimal('10.00'))
   ```

2. **API test** (curl):
   ```bash
   curl http://localhost:8000/api/accounts/first-purchase-discount/
   ```

3. **Frontend test:**
   - Visit /register — should show discount banner + birth_date field
   - Add item to cart → open drawer → should show discount banner
   - Register → cart banner changes to "Hai diritto al 10% di sconto"
   - Go to checkout → 10% applied automatically in order summary
