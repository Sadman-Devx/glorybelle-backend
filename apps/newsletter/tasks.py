"""
GLORYBELLE — Newsletter Celery Tasks.

Per rule.md: "Never call Stripe, Fattura24, or SendGrid synchronously."

P1 fix #13: replaced bare `except Exception` with explicit Exception catch
that uses logger.exception (full traceback) rather than logger.error (single line).
"""
import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.newsletter.tasks.send_newsletter",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_newsletter(self, subject, html_content):
    """
    Send a newsletter email to all active subscribers via SendGrid.

    Per rule.md: runs as a Celery task — never blocks any request.
    """
    from .models import NewsletterSubscriber

    subscribers = NewsletterSubscriber.objects.filter(
        is_active=True
    ).values_list("email", flat=True)

    if not subscribers:
        logger.info("No active newsletter subscribers — skipping send.")
        return 0

    sendgrid_api_key = getattr(settings, "SENDGRID_API_KEY", "")
    from_email = getattr(
        settings, "DEFAULT_FROM_EMAIL", "newsletter@glorybelle.it"
    )

    if not sendgrid_api_key or sendgrid_api_key == "placeholder":
        logger.info(
            "SendGrid not configured — would send newsletter '%s' to %d subscribers.",
            subject,
            len(subscribers),
        )
        return len(subscribers)

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        sent = 0
        for email in subscribers:
            message = Mail(
                from_email=from_email,
                to_emails=email,
                subject=subject,
                html_content=html_content,
            )
            sg = SendGridAPIClient(sendgrid_api_key)
            sg.send(message)
            sent += 1

        logger.info("Newsletter '%s' sent to %d subscribers.", subject, sent)
        return sent

    except Exception as exc:
        # P1 fix #13 — logger.exception gives the full traceback for SendGrid
        # / urllib3 / requests errors (was: logger.error with single-line message).
        # Still catches Exception (not BaseException) so KeyboardInterrupt propagates.
        logger.exception("Failed to send newsletter '%s': %s", subject, str(exc))
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
