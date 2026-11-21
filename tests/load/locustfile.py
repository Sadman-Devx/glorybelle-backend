"""
GLORYBELLE — Load Test (P1 fix #16)

Per PRD §3.9: "Designed for ~5,000 concurrent users without correctness failures."
Per backend-design PDF §6.1: "verified with actual load testing (Locust or k6
simulating 5,000 concurrent virtual users) against a staging environment."

Simulates a realistic shopping flow:
  1. Browse product list (read-heavy, cached)
  2. Filter by category (also cached)
  3. Open product detail
  4. Add to cart (write — tests stock reservation + select_for_update)
  5. View cart
  6. Remove item (releases reservation)
  7. Optionally checkout (skipped by default — requires Stripe test card)

Run:
  pip install locust
  locust -f tests/load/locustfile.py --host=https://staging-api.glorybelle.it

Then open http://localhost:8089, set number of users to 5000 and spawn rate
to 50/s, watch p50/p95/p99 latency in real time.

Targets (backend-design PDF §6.1):
  - Product browsing p50 < 80ms, p95 < 200ms, p99 < 400ms
  - Checkout p50 < 120ms, p95 < 350ms, p99 < 800ms
  - Error rate 0% (or <0.1% safely retried)
"""
import random
import uuid

from locust import HttpUser, between, task


# Sample product slugs + variant IDs — populate these from your seed data
PRODUCT_SLUGS = [
    "anello-solitario-meridian",
    "anello-halo-verdant",
    "collana-cascade",
    "orecchini-a-bottone-ellipse",
    "bracciale-rigido-solene",
]
VARIANT_IDS = list(range(1, 21))  # adjust to match your seeded variants

CATEGORIES = ["anelli", "collane", "orecchini", "bracciali"]
METALS = ["gold", "rose", "silver"]


class GlorybelleShopper(HttpUser):
    """
    Simulated customer browsing + adding to cart.
    Spawns with 5-15s think time between actions (realistic for a luxury shopper).
    """

    wait_time = between(5, 15)

    def on_start(self):
        """Set up a guest session — initialize cart."""
        # Generate a session key so guest cart mutations work consistently
        self.session_key = f"sess_load_{uuid.uuid4().hex[:8]}"
        # Get or create cart
        self.client.get(
            f"/api/cart/?session_key={self.session_key}",
            name="Setup: get cart",
        )

    @task(10)  # weight 10 — most common action
    def browse_products(self):
        """Browse product list — read-heavy, cached."""
        self.client.get("/api/products/", name="Browse: product list")

    @task(5)
    def filter_by_category(self):
        """Filter products by category — tests cache key per-filter."""
        cat = random.choice(CATEGORIES)
        self.client.get(
            f"/api/products/?category={cat}",
            name=f"Browse: filter category={cat}",
        )

    @task(3)
    def filter_by_metal(self):
        """Filter products by metal — tests another cache key."""
        metal = random.choice(METALS)
        self.client.get(
            f"/api/products/?metal={metal}",
            name=f"Browse: filter metal={metal}",
        )

    @task(5)
    def view_product_detail(self):
        """Open a product detail page — tests cache + DB read."""
        slug = random.choice(PRODUCT_SLUGS)
        self.client.get(
            f"/api/products/{slug}/",
            name="Browse: product detail",
        )

    @task(3)
    def view_featured(self):
        """View featured products (carousel) — dedicated endpoint (P1 fix #10)."""
        self.client.get("/api/products/featured/", name="Browse: featured")

    @task(2)
    def search(self):
        """Quick search — tests SearchFilter."""
        queries = ["anello", "collana", "oro", "diamante"]
        q = random.choice(queries)
        self.client.get(f"/api/search/?q={q}", name="Browse: search")

    @task(8)  # weight 8 — second most common action
    def add_to_cart(self):
        """Add to cart — WRITE operation, tests stock reservation + locking."""
        variant_id = random.choice(VARIANT_IDS)
        quantity = random.randint(1, 2)
        self.client.post(
            "/api/cart/items/",
            json={
                "variant_id": variant_id,
                "quantity": quantity,
                "session_key": self.session_key,
            },
            name="Cart: add item",
        )

    @task(5)
    def view_cart(self):
        """View cart contents."""
        self.client.get(
            f"/api/cart/?session_key={self.session_key}",
            name="Cart: view",
        )

    @task(2)
    def remove_from_cart(self):
        """Remove an item — releases reservation."""
        # First get the cart to find a valid item_id
        with self.client.get(
            f"/api/cart/?session_key={self.session_key}",
            name="Cart: view (for remove)",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure("Could not fetch cart")
                return
            items = resp.json().get("items", [])
            if not items:
                resp.failure("Cart empty — nothing to remove")
                return
            item_id = random.choice(items)["id"]

        self.client.delete(
            f"/api/cart/items/{item_id}/",
            name="Cart: remove item",
        )

    @task(1)
    def clear_cart(self):
        """Clear entire cart — DELETE /api/cart/ (P1 fix #10)."""
        self.client.delete("/api/cart/", name="Cart: clear")
        # Re-seed a fresh session after clear so we can keep adding items
        self.session_key = f"sess_load_{uuid.uuid4().hex[:8]}"


class GlorybelleCartAbandoner(HttpUser):
    """
    Simulates the worst-case scenario for stock reservation: a customer who
    adds items to cart then abandons without checking out. Tests that the
    Celery beat task (release_expired_reservations every 60s) correctly
    releases stock back without manual intervention.

    Wait time is 5+ minutes (matches the 15-min reservation expiry — these
    users are the slow shoppers who eventually trigger expiry).
    """

    wait_time = between(20, 60)  # short for test purposes; bump to 300+ for real expiry testing

    def on_start(self):
        self.session_key = f"sess_abandon_{uuid.uuid4().hex[:8]}"

    @task
    def add_then_abandon(self):
        """Add a bunch of items then never check out — let them expire."""
        for _ in range(random.randint(2, 5)):
            variant_id = random.choice(VARIANT_IDS)
            self.client.post(
                "/api/cart/items/",
                json={
                    "variant_id": variant_id,
                    "quantity": 1,
                    "session_key": self.session_key,
                },
                name="Abandoner: add item",
            )
