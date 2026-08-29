"""مصادقة المبدع في DRF — رمز حامل قصير الأجل، منفصل تمامًا عن جلسات الإدارة."""
from rest_framework import authentication, exceptions

from apps.common import tokens

from .models import Creator, CreatorDevice, CreatorStatus


class CreatorPrincipal:
    """هوية المبدع داخل الطلب. ليست مستخدم Django ولا تملك أي صلاحية إدارية."""

    def __init__(self, creator: Creator, device: CreatorDevice | None = None):
        self.creator = creator
        self.device = device

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_staff(self) -> bool:
        return False

    @property
    def is_superuser(self) -> bool:
        return False

    def __str__(self) -> str:
        return f"creator:{self.creator_id}"

    @property
    def creator_id(self):
        return self.creator.id

    @property
    def pk(self):
        """يستخدمها DRF في مفتاح قواعد السرعة."""
        return self.creator.pk

    @property
    def id(self):
        return self.creator.id


class CreatorJWTAuthentication(authentication.BaseAuthentication):
    """تقرأ رمز الوصول من ترويسة Authorization وتعيد هوية المبدع."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("ترويسة المصادقة غير صحيحة")

        try:
            payload = tokens.verify(header[1].decode(), tokens.TYPE_ACCESS)
        except tokens.InvalidToken as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc

        try:
            creator = Creator.objects.get(pk=payload.subject)
        except (Creator.DoesNotExist, ValueError, TypeError) as exc:
            raise exceptions.AuthenticationFailed("المبدع غير موجود") from exc

        if creator.status == CreatorStatus.SUSPENDED:
            raise exceptions.AuthenticationFailed("الحساب موقوف")

        device = None
        if payload.device_id:
            device = CreatorDevice.objects.filter(
                creator=creator, device_id=payload.device_id, is_active=True
            ).first()
            if device is None:
                raise exceptions.AuthenticationFailed("الجهاز غير مسجَّل أو مُعطَّل")

        return (CreatorPrincipal(creator, device), None)

    def authenticate_header(self, request):
        return self.keyword
