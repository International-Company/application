"""المبدع: ملفه، هاتفه الموثّق، موافقاته، أجهزته، وتحققه الاختياري من الهوية."""
from django.db import models

from apps.common.models import TimestampedModel


class CreatorStatus(models.TextChoices):
    NEW = "new", "جديد"
    SETUP_COMPLETED = "setup_completed", "اكتمل التجهيز"
    SUSPENDED = "suspended", "موقوف"


class Creator(TimestampedModel):
    """المبدع — الهوية مثلثة: حساب TikTok + هاتف موثّق + بصمة جهاز."""

    phone = models.CharField(max_length=20, unique=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    display_name = models.CharField(max_length=150, blank=True)
    preferred_language = models.CharField(
        max_length=2, choices=[("ar", "العربية"), ("en", "English")], default="ar"
    )
    status = models.CharField(
        max_length=20, choices=CreatorStatus.choices, default=CreatorStatus.NEW, db_index=True
    )
    # درجة خطورة تُحدَّث آليًا من قواعد السرعة والشذوذ
    risk_score = models.PositiveSmallIntegerField(default=0)
    suspended_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "creators"
        verbose_name = "مبدع"
        verbose_name_plural = "المبدعون"

    def __str__(self) -> str:
        return self.display_name or self.phone

    @property
    def is_active(self) -> bool:
        return self.status != CreatorStatus.SUSPENDED


class CreatorConsent(TimestampedModel):
    """سجل الموافقة على الشروط — نسخة النص ووقتها وبصمتها، لا يُعدَّل."""

    creator = models.ForeignKey(Creator, on_delete=models.PROTECT, related_name="consents")
    terms_version = models.CharField(max_length=30)
    accepted_at = models.DateTimeField()
    ip = models.GenericIPAddressField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=128, blank=True)
    content_hash = models.CharField(max_length=64, help_text="SHA-256 لنص الشروط المعروض")
    language = models.CharField(max_length=2, default="ar")

    class Meta:
        db_table = "creator_consents"
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "terms_version"], name="uniq_consent_per_terms_version"
            )
        ]


class IntegrityVerdict(models.TextChoices):
    TRUSTED = "trusted", "موثوق"
    UNTRUSTED = "untrusted", "غير موثوق"
    UNKNOWN = "unknown", "غير معروف"


class CreatorDevice(TimestampedModel):
    """جهاز المبدع — يُربط به الـ refresh token وتُفحص سلامته قبل كل سحب."""

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=128)
    model = models.CharField(max_length=100, blank=True)
    os_version = models.CharField(max_length=40, blank=True)
    app_version = models.CharField(max_length=20, blank=True)
    integrity_verdict = models.CharField(
        max_length=20, choices=IntegrityVerdict.choices, default=IntegrityVerdict.UNKNOWN
    )
    integrity_checked_at = models.DateTimeField(null=True, blank=True)
    fcm_token = models.CharField(max_length=255, blank=True)
    # الأذونات الممنوحة فعليًا على الجهاز: الإشعارات، العرض فوق التطبيقات، التعبئة
    permissions_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "creator_devices"
        constraints = [
            models.UniqueConstraint(fields=["creator", "device_id"], name="uniq_device_per_creator")
        ]

    @property
    def is_trusted(self) -> bool:
        return self.integrity_verdict == IntegrityVerdict.TRUSTED


class KycStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "غير مطلوب"
    PENDING = "pending", "قيد المراجعة"
    APPROVED = "approved", "مقبول"
    REJECTED = "rejected", "مرفوض"


class KycCheck(TimestampedModel):
    """تحقق الهوية — بنية جاهزة دون تكامل مزوّد في الإصدار الأول."""

    creator = models.ForeignKey(Creator, on_delete=models.PROTECT, related_name="kyc_checks")
    provider = models.CharField(max_length=40, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20, choices=KycStatus.choices, default=KycStatus.NOT_REQUIRED
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "kyc_checks"


class PhoneVerification(TimestampedModel):
    """رمز تحقق لمرة واحدة. يُخزَّن مجزَّأً لا نصًا صريحًا."""

    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    creator = models.ForeignKey(
        Creator, on_delete=models.CASCADE, null=True, blank=True, related_name="phone_verifications"
    )

    class Meta:
        db_table = "phone_verifications"
        indexes = [models.Index(fields=["phone", "created_at"])]

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None


class CreatorRefreshToken(TimestampedModel):
    """رمز تجديد مربوط بجهاز واحد. يُخزَّن مجزَّأً ويُدوَّر عند كل استعمال."""

    creator = models.ForeignKey(Creator, on_delete=models.CASCADE, related_name="refresh_tokens")
    device = models.ForeignKey(
        CreatorDevice, on_delete=models.CASCADE, related_name="refresh_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replaces"
    )

    class Meta:
        db_table = "creator_refresh_tokens"
        indexes = [models.Index(fields=["creator", "revoked_at"])]

    @property
    def is_active(self) -> bool:
        from django.utils import timezone as _tz

        return self.revoked_at is None and self.expires_at > _tz.now()
