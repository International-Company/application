"""فصل صلاحيات المبدع عن صلاحيات الإدارة فصلًا قاطعًا."""
from rest_framework import permissions

from apps.creators.authentication import CreatorPrincipal


class IsCreator(permissions.BasePermission):
    """مسارات المبدع: تُرفض جلسات الإدارة وأي هوية أخرى."""

    message = "هذا المسار للمبدعين فقط"

    def has_permission(self, request, view) -> bool:
        return isinstance(request.user, CreatorPrincipal)


class IsAdminSession(permissions.BasePermission):
    """مسارات الإدارة: تُرفض رموز المبدعين مهما كانت صحيحة."""

    message = "هذا المسار للإدارة فقط"

    def has_permission(self, request, view) -> bool:
        user = request.user
        if isinstance(user, CreatorPrincipal):
            return False
        return bool(user and user.is_authenticated and user.is_staff)


class IsVerifiedCreator(IsCreator):
    """يتطلب هاتفًا موثّقًا — كل ما يمس المال يمر من هنا."""

    message = "يلزم تأكيد رقم الهاتف أولًا"

    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return request.user.creator.phone_verified_at is not None
