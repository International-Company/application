"""أصحاب الحسابات المصرية وحسابات الاستلام وتخصيصها للمبدعين."""
from django.db import models

from apps.common.models import TimestampedModel
from apps.creators.models import Creator


class OwnerStatus(models.TextChoices):
    ACTIVE = "active", "نشط"
    PAUSED = "paused", "موقوف مؤقتًا"
    BLOCKED = "blocked", "محظور"


class AccountOwner(TimestampedModel):
    """صاحب الحساب المصري — يتلقى رسائل واتساب ويؤكد الوصول."""

    full_name = models.CharField(max_length=150)
    whatsapp_phone = models.CharField(max_length=20, unique=True)
    whatsapp_verified_at = models.DateTimeField(null=True, blank=True)
    preferred_language = models.CharField(
        max_length=2, choices=[("ar", "العربية"), ("en", "English")], default="ar"
    )
    status = models.CharField(
        max_length=20, choices=OwnerStatus.choices, default=OwnerStatus.ACTIVE, db_index=True
    )
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "account_owners"
        verbose_name = "صاحب حساب استلام"
        verbose_name_plural = "أصحاب حسابات الاستلام"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.whatsapp_phone})"


class ReceivingAccountType(models.TextChoices):
    IPA = "ipa", "عنوان إنستاباي"
    MOBILE = "mobile", "محفظة هاتف"
    BANK = "bank", "حساب بنكي"


class ReceivingAccountStatus(models.TextChoices):
    ACTIVE = "active", "نشط"
    FULL = "full", "بلغ السعة"
    PAUSED = "paused", "موقوف"


class ReceivingAccount(TimestampedModel):
    """حساب استلام مصري تضعه الإدارة ويُخصَّص للمبدعين."""

    owner = models.ForeignKey(AccountOwner, on_delete=models.PROTECT, related_name="accounts")
    type = models.CharField(max_length=10, choices=ReceivingAccountType.choices)
    identifier = models.CharField(
        max_length=120, help_text="عنوان إنستاباي أو رقم الحساب"
    )
    display_label = models.CharField(max_length=100, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    beneficiary_name = models.CharField(max_length=150, blank=True)
    daily_limit_egp = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    monthly_limit_egp = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    max_creators = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=10,
        choices=ReceivingAccountStatus.choices,
        default=ReceivingAccountStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        db_table = "receiving_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["type", "identifier"], name="uniq_receiving_identifier"
            ),
            models.CheckConstraint(
                condition=models.Q(max_creators__gte=1), name="receiving_max_creators_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.display_label or self.identifier

    @property
    def active_assignments_count(self) -> int:
        return self.assignments.filter(active=True).count()

    @property
    def has_capacity(self) -> bool:
        return (
            self.status == ReceivingAccountStatus.ACTIVE
            and self.active_assignments_count < self.max_creators
        )


class CreatorReceivingAssignment(TimestampedModel):
    """تخصيص حساب استلام لمبدع — مصدر الحقيقة الوحيد لما يُعبَّأ داخل TikTok."""

    creator = models.ForeignKey(Creator, on_delete=models.PROTECT, related_name="assignments")
    receiving_account = models.ForeignKey(
        ReceivingAccount, on_delete=models.PROTECT, related_name="assignments"
    )
    assigned_at = models.DateTimeField()
    autofilled_at = models.DateTimeField(
        null=True, blank=True, help_text="وقت تعبئة البيانات داخل TikTok"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, help_text="وقت أول تحويل ناجح")
    active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivation_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "creator_receiving_assignments"
        constraints = [
            # لكل مبدع تخصيص فعّال واحد فقط في أي وقت
            models.UniqueConstraint(
                fields=["creator"],
                condition=models.Q(active=True),
                name="uniq_active_assignment_per_creator",
            )
        ]
        indexes = [models.Index(fields=["receiving_account", "active"])]
