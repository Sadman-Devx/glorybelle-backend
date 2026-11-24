from django.contrib.auth.models import Group

from .models import StaffRoleChange
from .permissions import ADMIN_GROUPS, MANAGER_GROUP, VIEWER_GROUP
from .serializers import admin_role


ROLE_GROUPS = {
    "manager": MANAGER_GROUP,
    "viewer": VIEWER_GROUP,
}


def record_staff_role_change(user, actor, old_role, new_role):
    if old_role == new_role:
        return None
    return StaffRoleChange.objects.create(
        target_user=user,
        target_email=user.email,
        changed_by=actor,
        changed_by_email=actor.email,
        from_role=old_role or "",
        to_role=new_role or "",
    )


def assign_staff_role(user, role, actor):
    old_role = admin_role(user)
    role_groups = list(Group.objects.filter(name__in=ADMIN_GROUPS))
    if role_groups:
        user.groups.remove(*role_groups)
    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    user.groups.add(group)
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return record_staff_role_change(user, actor, old_role, role)
