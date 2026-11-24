from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from .security import (
    create_admin_auth_session,
    revoke_admin_session,
    revoke_user_admin_sessions,
)


User = get_user_model()


@receiver(user_logged_in)
def track_django_admin_login(sender, request, user, **kwargs):
    if (
        request is not None
        and request.path_info.startswith("/admin/")
        and user.is_superuser
        and getattr(user, "otp_device", None) is not None
    ):
        admin_session = create_admin_auth_session(user)
        request.session["admin_auth_session_id"] = str(admin_session.session_id)


@receiver(user_logged_out)
def revoke_django_admin_logout(sender, request, user, **kwargs):
    if request is None or user is None or not request.path_info.startswith("/admin/"):
        return
    session_id = request.session.get("admin_auth_session_id")
    if session_id:
        revoke_admin_session(session_id, user, "logout")


@receiver(pre_save, sender=User)
def capture_admin_security_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._admin_security_state = None
        return
    instance._admin_security_state = sender.objects.filter(pk=instance.pk).values(
        "password", "is_active", "is_staff", "is_superuser"
    ).first()


@receiver(post_save, sender=User)
def revoke_sessions_after_user_security_change(sender, instance, created, **kwargs):
    previous = getattr(instance, "_admin_security_state", None)
    if created or previous is None:
        return
    if previous["password"] != instance.password:
        revoke_user_admin_sessions(instance, "password_changed")
    elif any(
        previous[field] != getattr(instance, field)
        for field in ("is_active", "is_staff", "is_superuser")
    ):
        revoke_user_admin_sessions(instance, "account_changed")


@receiver(m2m_changed, sender=User.groups.through)
def revoke_sessions_after_group_change(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and isinstance(instance, User):
        revoke_user_admin_sessions(instance, "role_changed")
