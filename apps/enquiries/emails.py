from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_shop_notification(enquiry):
    context = {
        "enquiry": enquiry,
        "topic": enquiry.get_topic_display(),
        "atelier_type": enquiry.get_atelier_type_display(),
    }
    subject = render_to_string(
        "enquiries/email_notification_subject.txt",
        context,
    ).strip()
    text_body = render_to_string("enquiries/email_notification.txt", context)
    html_body = render_to_string("enquiries/email_notification.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.ENQUIRY_NOTIFICATION_EMAIL],
        reply_to=[enquiry.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
