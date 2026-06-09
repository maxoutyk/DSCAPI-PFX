from rest_framework.permissions import BasePermission


class IsAPIKeyAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return bool(
            getattr(request.user, 'tenant', None)
            and getattr(request.user, 'api_key', None)
        )
