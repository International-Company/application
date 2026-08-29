"""طلبات السحب وإشاراتها.

الحالة لا تُغيَّر بإسناد مباشر: كل انتقال يمر عبر
apps.withdrawals.state_machine.transition وإلا رُفض الحفظ.
"""
import secrets

from django.db import models

from apps.common.enums import Currency
from apps.common.errors import IllegalStateTransition
from apps.common.models import TimestampedModel
from apps.creators.models import Creator
from apps.receiving.models import ReceivingAccount

CODE_ALPHABET = "0123456789"


def generate_code() -> str:
    """توليد رمز طلب بصيغة WD-XXXXX."""
    return "WD-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))


class WithdrawalStatus(models.TextChoices):
    """حالات طلب السحب كما هي مثبتة في وثيقة المشروع — لا تُعدَّل دون موافقة."""

    INITIATED = "initiated", "بدأ الطلب"
    TIKTOK_PROCESSING = "tiktok_processing", "TikTok يعالج"
    TIKTOK_SENT = "tiktok_sent", "TikTok أرسل"
    TIKTOK_REJECTED = "tiktok_rejected", "TikTok رفض"
    RECEIVED_EG = "received_eg", "وصل للحساب المصري"
    APPROVED = "approved", "معتمد للدفع"
    PAID = "paid", "مدفوع"
    NOT_RECEIVED = "not_received", "لم يصل"
    CANCELLED = "cancelled", "ملغى"


TERMINAL_STATUSES = {
    WithdrawalStatus.PAID,
    WithdrawalStatus.CANCELLED,
    WithdrawalStatus.TIKTOK_REJECTED,
}


class WithdrawalRequest(TimestampedModel):
    """طلب سحب واحد من لحظة ضغط المبدع إلى لحظة دفعه."""

    code = models.CharField(max_length=12, unique=True, default=generate_code, editable=False)
    creator = models.ForeignKey(Creator, on_delete=models.PROTECT, related_name="withdrawals")
    receiving_account = models.ForeignKey(
        ReceivingAccount,
        on_delete=models.PROTECT,
        related_name="withdrawals",
        null=True,
        blank=True,
    )
    amount_usd = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    amount_egp = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    fx_rate = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    fee_egp = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    net_amount_egp = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    status = models.CharField(
        max_length=20,
        choices=WithdrawalStatus.choices,
        default=WithdrawalStatus.INITIATED,
        db_index=True,
    )
    # رقم عملية TikTok من البريد — مفتاح منع التكرار القطعي
    tiktok_txn_id = models.CharField(max_length=100, null=True, blank=True)
    initiated_at = models.DateTimeField()
    processing_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=200, blank=True)
    ledger_txn_id = models.UUIDField(null=True, blank=True, help_text="قيد الإيداع عند received_eg")

    class Meta:
        db_table = "withdrawal_requests"
        verbose_name = "طلب سحب"
        verbose_name_plural = "طلبات السحب"
        constraints = [
            # منع التكرار عبر رقم عملية TikTok حين يتوفر
            models.UniqueConstraint(
                fields=["tiktok_txn_id"],
                condition=models.Q(tiktok_txn_id__isnull=False),
                name="uniq_withdrawal_tiktok_txn",
            ),
            # حارس الضغط المزدوج: طلب واحد فقط في حالة initiated لكل مبدع
            models.UniqueConstraint(
                fields=["creator"],
                condition=models.Q(status="initiated"),
                name="uniq_open_initiated_per_creator",
            ),
            models.CheckConstraint(
                condition=models.Q(fee_egp__gte=0) & models.Q(net_amount_egp__gte=0),
                name="withdrawal_amounts_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "initiated_at"]),
            models.Index(fields=["creator", "initiated_at"]),
            models.Index(fields=["receiving_account", "sent_at"]),
        ]

    def __str__(self) -> str:
        return self.code

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # نحفظ الحالة المقروءة لكشف أي تعديل مباشر عليها
        instance._loaded_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        loaded = getattr(self, "_loaded_status", None)
        bypassed = not getattr(self, "_via_state_machine", False)
        if loaded is not None and loaded != self.status and bypassed:
            raise IllegalStateTransition(
                "لا يجوز تغيير حالة الطلب مباشرة؛ استخدم state_machine.transition"
            )
        super().save(*args, **kwargs)
        self._loaded_status = self.status

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class SignalSource(models.TextChoices):
    """مصدر الإشارة — ما يثبت شيئًا عن الطلب."""

    NOTIFICATION = "notification", "إشعار TikTok"
    EMAIL = "email", "بريد TikTok"
    OWNER_WA = "owner_wa", "رد صاحب الحساب على واتساب"
    SMS = "sms", "رسالة بنك"
    MANUAL = "manual", "إدخال إدارة"


class SignalKind(models.TextChoices):
    """ما تدّعيه الإشارة."""

    PROCESSING = "processing", "قيد المعالجة"
    SENT = "sent", "تم الإرسال"
    REJECTED = "rejected", "مرفوض"
    RECEIVED = "received", "وصل"


class WithdrawalSignal(TimestampedModel):
    """إشارة خام مرتبطة بطلب. الإشارات تُحرّك الحالة ولا تُنشئ مالًا."""

    request = models.ForeignKey(
        WithdrawalRequest, on_delete=models.CASCADE, related_name="signals", null=True, blank=True
    )
    creator = models.ForeignKey(
        Creator, on_delete=models.PROTECT, related_name="withdrawal_signals", null=True, blank=True
    )
    source = models.CharField(max_length=20, choices=SignalSource.choices, db_index=True)
    kind = models.CharField(max_length=20, choices=SignalKind.choices)
    raw_payload = models.JSONField(default=dict, blank=True)
    parsed_amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    parsed_currency = models.CharField(max_length=3, blank=True)
    parsed_txn_id = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    parsed_at = models.DateTimeField(null=True, blank=True)
    # التحقق من توقيع حزمة TikTok — إشارة الإشعار بلا توقيع صحيح لا يُعتد بها
    package_sig_ok = models.BooleanField(default=False)
    dedupe_key = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "withdrawal_signals"
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="uniq_signal_dedupe_key",
            )
        ]
        indexes = [models.Index(fields=["request", "created_at"])]

    @property
    def is_trustworthy(self) -> bool:
        """إشارة الإشعار تحتاج توقيع حزمة صحيحًا؛ باقي المصادر تُقيَّم في محلها."""
        if self.source == SignalSource.NOTIFICATION:
            return self.package_sig_ok
        return True
