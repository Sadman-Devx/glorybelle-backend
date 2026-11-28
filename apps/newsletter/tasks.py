"""
GLORYBELLE — Newsletter Celery Tasks.

Per rule.md: "Never call Stripe, Fattura24, or SendGrid synchronously."

P1 fix #13: replaced bare `except Exception` with explicit Exception catch
that uses logger.exception (full traceback) rather than logger.error (single line).
"""
from html import escape
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
    from .tokens import unsubscribe_url

    subscribers = list(
        NewsletterSubscriber.objects.filter(
            is_active=True, is_confirmed=True
        ).values_list(
            "email", flat=True
        )
    )

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

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Header, Mail

    sg = SendGridAPIClient(sendgrid_api_key)
    sent = 0
    failures = []
    for email in subscribers:
        # Every message carries ITS OWN signed unsubscribe link (required by GDPR /
        # the Italian e-privacy rules) — also exposed as a List-Unsubscribe header so
        # mail clients can show their native "Unsubscribe" button.
        link = unsubscribe_url(email)
        body = html_content + (
            '<hr><p style="font-size:12px;color:#777">'
            "Ricevi questa email perché sei iscritto alla newsletter GLORYBELLE. "
            f'<a href="{escape(link, quote=True)}">Annulla l\'iscrizione</a>.</p>'
        )
        try:
            message = Mail(
                from_email=from_email,
                to_emails=email,
                subject=subject,
                html_content=body,
            )
            message.add_header(Header("List-Unsubscribe", f"<{link}>"))
            sg.send(message)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — one bad recipient must not stop the rest
            logger.exception("Newsletter '%s' failed for one recipient: %s", subject, exc)
            failures.append(exc)

    logger.info(
        "Newsletter '%s': %d sent, %d failed.", subject, sent, len(failures)
    )
    if sent == 0 and failures:
        # Nothing went out at all (SendGrid down / bad key): retrying the whole batch is
        # safe. A PARTIAL failure is never retried as a batch — that re-sent the
        # newsletter to everyone who had already received it.
        raise self.retry(
            exc=failures[0], countdown=60 * (2 ** self.request.retries)
        )
    return sent


@shared_task(
    name="apps.newsletter.tasks.send_confirmation_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_confirmation_email(self, subscriber_id, confirmation_nonce):
    """Send an HTML-escaped, expiring opt-in link to a pending subscriber."""
    from .models import NewsletterSubscriber
    from .tokens import confirmation_url

    subscriber = NewsletterSubscriber.objects.filter(
        pk=subscriber_id,
        is_active=True,
        is_confirmed=False,
        confirmation_nonce=confirmation_nonce,
    ).first()
    if subscriber is None:
        logger.info(
            "Confirmation email skipped for stale subscriber id=%s",
            subscriber_id,
        )
        return False

    sendgrid_api_key = getattr(settings, "SENDGRID_API_KEY", "")
    if not sendgrid_api_key or sendgrid_api_key == "placeholder":
        logger.info(
            "SendGrid not configured — confirmation email not sent to pending subscriber."
        )
        return False

    from_email = getattr(
        settings, "DEFAULT_FROM_EMAIL", "newsletter@glorybelle.it"
    )
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    link = confirmation_url(subscriber.email, str(subscriber.confirmation_nonce))
    safe_email = escape(subscriber.email)
    safe_link = escape(link, quote=True)
    message = Mail(
        from_email=from_email,
        to_emails=subscriber.email,
        subject="Conferma l'iscrizione alla newsletter GLORYBELLE",
        html_content=(
            "<p>Hai richiesto di iscriverti alla newsletter GLORYBELLE con "
            f"<strong>{safe_email}</strong>.</p>"
            f'<p><a href="{safe_link}">Conferma l\'iscrizione</a></p>'
            "<p>Il link scade tra 7 giorni. Se non hai richiesto tu l'iscrizione, "
            "puoi ignorare questa email.</p>"
        ),
    )
    try:
        SendGridAPIClient(sendgrid_api_key).send(message)
    except Exception as exc:  # noqa: BLE001 — task retries transient provider failures
        logger.exception(
            "Newsletter confirmation email failed for subscriber id=%s",
            subscriber_id,
        )
        raise self.retry(exc=exc) from exc

    logger.info("Newsletter confirmation email sent for subscriber id=%s", subscriber_id)
    return True
