"""إصدار جلسات المبدع وتدوير رموز التجديد."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common import tokens
from apps.common.enums import ActorType
from apps.common.errors import DomainError
from apps.creators.models import Creator, CreatorDevice, CreatorRefreshToken


class SessionError(DomainError):
    """فشل في إصدار جلسة أو تجديدها."""


def issue_session(creator: Creator, device: CreatorDevice | None) -> dict:
    """إصدار رمز وصول ورمز تجديد مربوط بالجهاز."""
    device_id = device.device_id if device else ""
    access, _ = tokens.issue(str(creator.id), tokens.TYPE_ACCESS, device_id=device_id)

    refresh = ""
    if device is not None:
        refresh, _ = tokens.issue(str(creator.id), tokens.TYPE_REFRESH, device_id=device_id)
        CreatorRefreshToken.objects.create(
            creator=creator,
            device=device,
            token_hash=tokens.hash_token(refresh),
            expires_at=timezone.now() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )

    return {
        "access": access,
        "refresh": refresh,
        "expires_in": settings.ACCESS_TOKEN_MINUTES * 60,
        "token_type": "Bearer",
    }


def _revoke_device_sessions(stored: CreatorRefreshToken) -> None:
    """إبطال كل جلسات الجهاز.

    يُنفَّذ في معاملة مستقلة ثم يُرفع الخطأ خارجها، وإلا ألغى التراجعُ الإبطالَ
    نفسه وبقي الرمز المسروق صالحًا.
    """
    with transaction.atomic():
        CreatorRefreshToken.objects.filter(
            device=stored.device, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
        audit.record(
            action="session.reuse_detected",
            entity="creator_device",
            entity_id=stored.device_id,
            actor_type=ActorType.SYSTEM,
            after={"creator_id": str(stored.creator_id)},
        )


def rotate_refresh_token(refresh_token: str) -> dict:
    """تدوير رمز التجديد: القديم يُبطَل فورًا ويصدر بديل عنه.

    إعادة استعمال رمز مُبطَل تُبطل كل رموز الجهاز — مؤشر سرقة محتملة.
    """
    try:
        payload = tokens.verify(refresh_token, tokens.TYPE_REFRESH)
    except tokens.InvalidToken as exc:
        raise SessionError(str(exc)) from exc

    stored = CreatorRefreshToken.objects.filter(
        token_hash=tokens.hash_token(refresh_token)
    ).first()
    if stored is None:
        raise SessionError("رمز التجديد غير معروف")

    if stored.revoked_at is not None:
        _revoke_device_sessions(stored)
        raise SessionError("أُعيد استعمال رمز مُبطَل؛ أُبطلت جلسات الجهاز كلها")

    with transaction.atomic():
        stored = CreatorRefreshToken.objects.select_for_update().get(pk=stored.pk)
        if stored.revoked_at is not None:
            raise SessionError("رمز التجديد مُبطَل")
        if not stored.is_active:
            raise SessionError("انتهت صلاحية رمز التجديد")

        creator = stored.creator
        if creator.status == "suspended":
            raise SessionError("الحساب موقوف")

        device = stored.device
        if not device.is_active or device.device_id != payload.device_id:
            raise SessionError("الجهاز غير مطابق")

        session = issue_session(creator, device)
        stored.revoked_at = timezone.now()
        stored.replaced_by = CreatorRefreshToken.objects.filter(
            token_hash=tokens.hash_token(session["refresh"])
        ).first()
        stored.save(update_fields=["revoked_at", "replaced_by", "updated_at"])

        device.last_seen_at = timezone.now()
        device.save(update_fields=["last_seen_at", "updated_at"])

    return session
