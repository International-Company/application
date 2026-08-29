"""ربط حسابات المنصات الخارجية (TikTok أولًا) وتوكناتها المشفّرة."""
from django.db import models

from apps.common.fields import EncryptedTextField
from apps.common.models import TimestampedModel
from apps.creators.models import Creator


class Platform(models.TextChoices):
    """المنصات — الطبقة مصمَّمة لقبول غيرها لاحقًا دون تعديل الجداول."""

    TIKTOK = "tiktok", "TikTok"


class PlatformAccountStatus(models.TextChoices):
    ACTIVE = "active", "نشط"
    TOKEN_EXPIRED = "token_expired", "انتهى التوكن"
    REVOKED = "revoked", "أُلغي الربط"


class CreatorPlatformAccount(TimestampedModel):
    """حساب المبدع على منصة خارجية. التوكنات لا تغادر الخادم أبدًا."""

    creator = models.ForeignKey(Creator, on_delete=models.PROTECT, related_name="platform_accounts")
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.TIKTOK)
    open_id = models.CharField(max_length=128, unique=True)
    union_id = models.CharField(max_length=128, blank=True)
    display_name = models.CharField(max_length=150, blank=True)
    avatar_url = models.URLField(blank=True, max_length=500)
    profile_url = models.URLField(blank=True, max_length=500)
    follower_count = models.BigIntegerField(default=0)
    access_token_enc = EncryptedTextField(blank=True, default="")
    refresh_token_enc = EncryptedTextField(blank=True, default="")
    token_expires_at = models.DateTimeField(null=True, blank=True)
    refresh_expires_at = models.DateTimeField(null=True, blank=True)
    scopes = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=PlatformAccountStatus.choices, default=PlatformAccountStatus.ACTIVE
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "creator_platform_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "platform"], name="uniq_platform_account_per_creator"
            )
        ]


class SyncOutcome(models.TextChoices):
    SUCCESS = "success", "نجحت"
    FAILED = "failed", "فشلت"


class SyncLog(TimestampedModel):
    """سجل عمليات المزامنة وتجديد التوكن — للتشخيص لا للمنطق المالي."""

    account = models.ForeignKey(
        CreatorPlatformAccount, on_delete=models.CASCADE, related_name="sync_logs"
    )
    operation = models.CharField(max_length=40)
    outcome = models.CharField(max_length=20, choices=SyncOutcome.choices)
    detail = models.TextField(blank=True)

    class Meta:
        db_table = "sync_logs"
        indexes = [models.Index(fields=["account", "created_at"])]
