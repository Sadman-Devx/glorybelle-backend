# Load Tests — GLORYBELLE Backend

Per PRD §3.9: "Designed for ~5,000 concurrent users without correctness failures."
Per backend-design PDF §6.1: "verified with actual load testing (Locust or k6
simulating 5,000 concurrent virtual users) against a staging environment."

## Setup

```bash
# Install Locust (in a separate venv — keep test deps out of the runtime image)
pip install -r tests/load/requirements.txt

# Or run inside Docker (recommended):
docker run --rm -it --network host \
  -v $(pwd)/tests/load:/mnt/locust \
  -w /mnt/locust \
  python:3.12-slim bash -c "pip install locust && locust -f locustfile.py --host=https://staging-api.glorybelle.it"
```

## Run

```bash
# Web UI mode — opens http://localhost:8089
locust -f tests/load/locustfile.py --host=https://staging-api.glorybelle.it

# Headless mode — for CI / automated regression
locust -f tests/load/locustfile.py \
  --host=https://staging-api.glorybelle.it \
  --headless \
  --users 5000 \
  --spawn-rate 50 \
  --run-time 10m \
  --csv=load_test_results
```

## What this simulates

Two user classes, both running concurrently:

1. **GlorybelleShopper** (weight ~95% of users): realistic shopping flow.
   Browse product list → filter by category/metal → view detail → add to cart →
   view cart → occasionally remove item → occasionally clear cart.

2. **GlorybelleCartAbandoner** (weight ~5%): adds items then abandons.
   Tests that the Celery beat task (`release_expired_reservations` every 60s)
   correctly releases stock back without manual intervention — the worst-case
   scenario for the 15-minute reservation expiry.

## Targets (backend-design PDF §6.1)

| Endpoint              | p50      | p95      | p99      | Error rate |
| --------------------- | -------- | -------- | -------- | ---------- |
| Product browse/search | < 80ms   | < 200ms  | < 400ms  | 0%         |
| Cart mutations        | < 120ms  | < 350ms  | < 800ms  | < 0.1%     |

These are *design targets* — measured values must be verified against the
actual staging environment. If p95 exceeds the target, investigate:

- N+1 queries on hot endpoints (see audit PDF P1 #9)
- Cache hit rate (Redis stats — should be > 90% for /api/products/)
- PostgreSQL connection count (PgBouncer needed above ~100 concurrent)
- `select_for_update()` lock contention on hot variants

## Tuning the test

Edit `locustfile.py` and adjust:

- `PRODUCT_SLUGS` / `VARIANT_IDS` — must match your seed data
- `between(5, 15)` think time — bump for more realistic pacing
- `@task(N)` weights — adjust to match your real-world traffic mix

## What "correct" looks like

- All HTTP responses 200 (or 201 for cart adds)
- No 500 errors (means select_for_update + transaction.atomic working)
- No stock_quantity drops below 0 (means reservation pattern working)
- p95 latency within target
- Cart abandonment cases: `reserved_quantity` drops back to 0 within ~15min
  of last activity (Celery beat task working)
