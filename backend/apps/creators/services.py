"""تحقق الهاتف، تسجيل الأجهزة، والموافقات."""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.common.errors import DomainError

from .integrity import get_integrity_verifier
from .models import (
    Creator,
    CreatorConsent,
    CreatorDevice,
    CreatorStatus,
    IntegrityVerdict,
    PhoneVerification,
)
from .sms import get_sms_sender


class PhoneVerificationError(DomainError):
    """فشل في تحقق الهاتف."""


def _hash_code(phone: str, code: str) -> str:
    """بصمة الرمز — لا يُخزَّن الرمز نصًا صريحًا أبدًا."""
    material = phone + ":" + code + ":" + settings.SECRET_KEY
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def start_phone_verification(creator: Creator, phone: str) -> PhoneVerification:
    """توليد رمز وإرساله. الرمز لا يُعاد في الاستجابة إطلاقًا."""
    if not phone:
        raise PhoneVerificationError("رقم الهاتف مطلوب")

    cooldown = timezone.now() - timedelta(seconds=settings.OTP_RESEND_SECONDS)
    if PhoneVerification.objects.filter(
        phone=phone, consumed_at__isnull=True, created_at__gte=cooldown
    ).exists():
        raise PhoneVerificationError("طُلب رمز قبل قليل؛ انتظر قبل إعادة المحاولة")

    upper_bound = 10**settings.OTP_LENGTH
    code = str(secrets.randbelow(upper_bound)).zfill(settings.OTP_LENGTH)
    verification = PhoneVerification.objects.create(
        creator=creator,
        phone=phone,
        code_hash=_hash_code(phone, code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
    )
    # يظهر الرمز في نص الرسالة ليقرأه SMS Retriever آليًا دون كتابة من المبدع
    get_sms_sender().send(phone, "رمز التحقق: " + code)
    return verification


@transaction.atomic
def confirm_phone_verification(creator: Creator, phone: str, code: str) -> Creator:
    """التحقق من الرمز وتوثيق الهاتف. الرقم فريد على مستوى المنصة."""
    verification = (
        PhoneVerification.objects.select_for_update()
        .filter(phone=phone, creator=creator, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if verification is None:
        raise PhoneVerificationError("لا يوجد طلب تحقق قائم لهذا الرقم")
    if verification.expires_at <= timezone.now():
        raise PhoneVerificationError("انتهت صلاحية الرمز")
    if verification.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise PhoneVerificationError("تجاوزت عدد المحاولات المسموح بها")

    verification.attempts += 1
    verification.save(update_fields=["attempts", "updated_at"])

    if not secrets.compare_digest(verification.code_hash, _hash_code(phone, code)):
        raise PhoneVerificationError("الرمز غير صحيح")

    if Creator.objects.filter(phone=phone).exclude(pk=creator.pk).exists():
        raise PhoneVerificationError("هذا الرقم موثّق لحساب آخر")

    verification.consumed_at = timezone.now()
    verification.save(update_fields=["consumed_at", "updated_at"])

    creator.phone = phone
    creator.phone_verified_at = timezone.now()
    creator.save(update_fields=["phone", "phone_verified_at", "updated_at"])

    audit.record(
        action="creator.phone_verified",
        entity="creator",
        entity_id=creator.id,
        actor_type=ActorType.CREATOR,
        actor_id=creator.id,
    )
    return creator


def register_device(
    creator: Creator,
    *,
    device_id: str,
    integrity_token: str = "",
    fcm_token: str = "",
    model: str = "",
    os_version: str = "",
    app_version: str = "",
    permissions: dict | None = None,
) -> CreatorDevice:
    """تسجيل جهاز أو تحديثه مع فحص سلامته."""
    if not device_id:
        raise DomainError("معرّف الجهاز مطلوب")

    verdict = get_integrity_verifier().verify(integrity_token, device_id=device_id)
    device, _ = CreatorDevice.objects.update_or_create(
        creator=creator,
        device_id=device_id,
        defaults={
            "model": model,
            "os_version": os_version,
            "app_version": app_version,
            "fcm_token": fcm_token,
            "permissions_json": permissions or {},
            "integrity_verdict": verdict,
            "integrity_checked_at": timezone.now(),
            "last_seen_at": timezone.now(),
            "is_active": True,
        },
    )
    audit.record(
        action="device.registered",
        entity="creator_device",
        entity_id=device.id,
        actor_type=ActorType.CREATOR,
        actor_id=creator.id,
        after={"integrity_verdict": verdict, "device_id": device_id},
    )
    return device


def record_consent(
    creator: Creator,
    *,
    terms_version: str,
    content_hash: str,
    ip: str | None = None,
    device_fingerprint: str = "",
    language: str = "ar",
) -> CreatorConsent:
    """تسجيل الموافقة على الشروط بنسختها ووقتها وبصمتها."""
    consent, created = CreatorConsent.objects.get_or_create(
        creator=creator,
        terms_version=terms_version,
        defaults={
            "accepted_at": timezone.now(),
            "ip": ip,
            "device_fingerprint": device_fingerprint,
            "content_hash": content_hash,
            "language": language,
        },
    )
    if created:
        audit.record(
            action="creator.consent_recorded",
            entity="creator_consent",
            entity_id=consent.id,
            actor_type=ActorType.CREATOR,
            actor_id=creator.id,
            after={"terms_version": terms_version, "content_hash": content_hash},
            ip=ip,
        )
    return consent


def require_trusted_device(creator: Creator, device: CreatorDevice | None) -> CreatorDevice:
    """حارس السحب: جهاز مسجَّل وسليم وحساب غير موقوف، وإلا فلا طلب."""
    if creator.status == CreatorStatus.SUSPENDED:
        raise DomainError("الحساب موقوف")
    if device is None:
        raise DomainError("لا يوجد جهاز مسجَّل لهذا الطلب")
    if settings.REQUIRE_DEVICE_INTEGRITY and device.integrity_verdict != IntegrityVerdict.TRUSTED:
        raise DomainError("الجهاز غير موثوق؛ تعذّر تنفيذ الطلب")
    return device
