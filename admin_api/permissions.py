from rest_framework.permissions import BasePermission


MANAGER_GROUP = "Manager"
VIEWER_GROUP = "Viewer"
ADMIN_GROUPS = (MANAGER_GROUP, VIEWER_GROUP)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_staff
            and (
                user.is_superuser
                or user.groups.filter(name__in=ADMIN_GROUPS).exists()
            )
        )


class IsManager(IsAdminRole):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_staff
            and (
                user.is_superuser
                or user.groups.filter(name=MANAGER_GROUP).exists()
            )
        )


class IsAdminReaderManagerWriter(IsAdminRole):
    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return super().has_permission(request, view)
        return IsManager().has_permission(request, view)


class IsSuperuser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_staff
            and user.is_superuser
        )
