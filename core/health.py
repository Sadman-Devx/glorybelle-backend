"""
Lightweight liveness/readiness probe used by Docker healthchecks.

Plain Django view (no DRF): no auth, no throttling, no schema generation.
Returns 200 when the database answers `SELECT 1`, otherwise 503.
"""
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - any DB failure means "not ready"
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
