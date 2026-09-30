"""
GLORYBELLE — Invoicing Celery Tasks.

Per architecture.md §1.2:
  "Called from a Celery task so a temporary outage doesn't block checkout."
Per rule.md:
  "Never call Stripe, Fattura24, or SendGrid synchronously inside a
   request/response cycle. These are Celery tasks."
"""
import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.invoicing.tasks.generate_invoice",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 60 seconds between retries
)
def generate_invoice(self, order_id):
    """
    Generate and submit an Italian electronic invoice for a paid order.

    Retries on failure with exponential backoff (max 3 retries).
    Per architecture.md: a Fattura24 outage must not block checkout.
    """
    from apps.invoicing.fattura24_client import create_invoice
    from apps.invoicing.models import Invoice
    from apps.orders.models import Order

    try:
        order = Order.objects.prefetch_related("items").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for invoicing", order_id)
        return

    # Check if invoice already exists (idempotency)
    if Invoice.objects.filter(order=order).exists():
        logger.info("Invoice already exists for order %s", order.order_number)
        return

    invoice_number = f"FE-{order.order_number}"

    try:
        result = create_invoice(order)

        Invoice.objects.create(
            order=order,
            invoice_number=invoice_number,
            fattura24_id=result.get("fattura24_id", ""),
            status="submitted",
            pdf_url=result.get("pdf_url", ""),
            xml_content=result.get("xml_content", ""),
            attempts=self.request.retries + 1,
        )

        logger.info(
            "Invoice %s generated for order %s",
            invoice_number,
            order.order_number,
        )

    except Exception as exc:
        logger.error(
            "Failed to generate invoice for order %s (attempt %d): %s",
            order.order_number,
            self.request.retries + 1,
            str(exc),
        )

        # Create a failed invoice record on final retry
        if self.request.retries >= self.max_retries:
            Invoice.objects.create(
                order=order,
                invoice_number=invoice_number,
                status="error",
                error_message=str(exc),
                attempts=self.request.retries + 1,
            )
            return

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(
    name="apps.invoicing.tasks.send_order_confirmation_email",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_order_confirmation_email(self, order_id):
    """
    Send order confirmation email via SendGrid.

    Per rule.md: runs as a Celery task — never blocks checkout.
    """
    from apps.orders.models import Order

    try:
        order = Order.objects.prefetch_related("items").get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found for confirmation email", order_id)
        return

    sendgrid_api_key = getattr(settings, "SENDGRID_API_KEY", "")
    from_email = getattr(
        settings, "DEFAULT_FROM_EMAIL", "ordini@glorybelle.it"
    )

    if not sendgrid_api_key or sendgrid_api_key == "placeholder":
        logger.info(
            "SendGrid not configured — logging confirmation email for order %s",
            order.order_number,
        )
        logger.info(
            "TO: %s | SUBJECT: Conferma ordine %s | TOTAL: €%.2f",
            order.email,
            order.order_number,
            order.total,
        )
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        # Build email content
        items_html = ""
        for item in order.items.all():
            items_html += (
                f"<tr>"
                f"<td>{item.product_name}</td>"
                f"<td>{item.variant_metal_display}, {item.variant_size}</td>"
                f"<td>{item.quantity}</td>"
                f"<td>€{item.unit_price:.2f}</td>"
                f"<td>€{item.line_total:.2f}</td>"
                f"</tr>"
            )

        html_content = f"""
        <h2>Grazie per il tuo ordine, {order.shipping_first_name}!</h2>
        <p>Il tuo ordine <strong>{order.order_number}</strong> è stato confermato.</p>

        <table border="1" cellpadding="8" cellspacing="0"
               style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr>
                    <th>Prodotto</th>
                    <th>Variante</th>
                    <th>Qtà</th>
                    <th>Prezzo</th>
                    <th>Totale</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>

        <p><strong>Totale: €{order.total:.2f}</strong></p>

        <p>Spedizione: {order.shipping_line1}, {order.shipping_city}
        ({order.shipping_province}) {order.shipping_postal_code}</p>

        <p>Grazie per aver scelto GLORYBELLE.</p>
        """

        message = Mail(
            from_email=from_email,
            to_emails=order.email,
            subject=f"GLORYBELLE — Conferma ordine {order.order_number}",
            html_content=html_content,
        )

        sg = SendGridAPIClient(sendgrid_api_key)
        sg.send(message)

        logger.info(
            "Confirmation email sent for order %s to %s",
            order.order_number,
            order.email,
        )

    except Exception as exc:
        logger.error(
            "Failed to send confirmation email for order %s: %s",
            order.order_number,
            str(exc),
        )
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))
