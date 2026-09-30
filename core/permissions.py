"""
GLORYBELLE — Custom Permissions.
"""
from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission: only the owner of an object can edit it.
    Assumes the object has a `user` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any request (GET, HEAD, OPTIONS).
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write permissions only for the owner.
        return obj.user == request.user


class IsOwner(permissions.BasePermission):
    """
    Object-level permission: only the owner can view or edit.
    Used for private resources like addresses and orders.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allow read access to everyone, write access only to admin users.
    Used for catalog endpoints.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff
