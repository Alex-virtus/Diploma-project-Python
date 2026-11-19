from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission


User = get_user_model()


class IsSupplier(BasePermission):
    message = "Только активный поставщик может обновлять прайс."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role == User.Role.SUPPLIER
        )
