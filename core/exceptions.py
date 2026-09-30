"""
GLORYBELLE — Custom Exceptions.

Consistent API error shapes across all apps.
Per rule.md: "Avoid bare except: blocks" — catch specific exceptions.
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class OutOfStock(APIException):
    """Raised when a product variant doesn't have enough available stock."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Questo articolo non è più disponibile nella quantità richiesta."
    default_code = "out_of_stock"


class ReservationExpired(APIException):
    """Raised when a stock reservation has expired."""

    status_code = status.HTTP_410_GONE
    default_detail = "La riserva del prodotto è scaduta. Riprova."
    default_code = "reservation_expired"


class CartEmpty(APIException):
    """Raised when attempting checkout with an empty cart."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Il carrello è vuoto."
    default_code = "cart_empty"


class PaymentError(APIException):
    """Raised on payment processing failures."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Si è verificato un errore durante il pagamento."
    default_code = "payment_error"


class DuplicateWebhookEvent(APIException):
    """Raised when a webhook event has already been processed."""

    status_code = status.HTTP_200_OK
    default_detail = "Evento già elaborato."
    default_code = "duplicate_event"


class InvoicingError(APIException):
    """Raised on invoicing failures (Fattura24). Non-blocking."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Si è verificato un errore durante la fatturazione."
    default_code = "invoicing_error"


def custom_exception_handler(exc, context):
    """
    Custom exception handler that wraps DRF's default handler to ensure
    a consistent error response shape:

    {
        "error": {
            "code": "out_of_stock",
            "detail": "Questo articolo non è più disponibile..."
        }
    }
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_code = getattr(exc, "default_code", "error")
        if isinstance(response.data, dict) and "detail" in response.data:
            response.data = {
                "error": {
                    "code": error_code,
                    "detail": str(response.data["detail"]),
                }
            }
        elif isinstance(response.data, list):
            response.data = {
                "error": {
                    "code": error_code,
                    "detail": response.data,
                }
            }

    return response
