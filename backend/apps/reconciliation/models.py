"""الوارد البنكي ومطابقته بطلبات السحب."""
from django.db import models

from apps.common.models import TimestampedModel
from apps.receiving.models import ReceivingAccount
from apps.withdrawals.models import WithdrawalRequest


class TransferSource(models.TextChoices):
    SMS = "sms", "رسالة بنك"
    NOTIFICATION = "notification", "إشعار تطبيق البنك"
    STATEMENT = "statement", "كشف حساب"
    MANUAL = "manual", "إدخال إدارة"


class IncomingTransfer(TimestampedModel):
    """تحويل وارد إلى حساب استلام مصري — الدليل الوحيد المقبول على وصول المال."""

    receiving_account = models.ForeignKey(
        ReceivingAccount, on_delete=models.PROTECT, related_name="incoming_transfers"
    )
    amount_egp = models.DecimalField(max_digits=18, decimal_places=4)
    received_at = models.DateTimeField(db_index=True)
    bank_ref = models.CharField(max_length=120, blank=True)
    sender_hint = models.CharField(max_length=200, blank=True, help_text="ما يظهر عن المرسِل إن وُجد")
    source = models.CharField(max_length=20, choices=TransferSource.choices)
    raw_payload = models.JSONField(default=dict, blank=True)
    # مفتاح منع التكرار: بصمة نص الرسالة الأصلية وزمنها
    dedupe_key = models.CharField(max_length=120, blank=True)
    matched_request = models.ForeignKey(
        WithdrawalRequest,
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
        null=True,
        blank=True,
    )
    matched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "incoming_transfers"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_egp__gt=0), name="incoming_transfer_amount_positive"
            ),
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="uniq_incoming_transfer_dedupe",
            ),
            # تحويل واحد لا يُطابق أكثر من طلب
            models.UniqueConstraint(
                fields=["matched_request"],
                condition=models.Q(matched_request__isnull=False),
                name="uniq_transfer_per_request",
            ),
        ]
        indexes = [models.Index(fields=["receiving_account", "received_at"])]


class MatchMethod(models.TextChoices):
    UNIQUE_ADDRESS = "unique_address", "عنوان استلام خاص"
    ACCOUNT_AMOUNT_TIME = "account_amount_time", "الحساب والمبلغ والزمن"
    OWNER_REPLY = "owner_reply", "رد صاحب الحساب"
    CREATOR_REPLY = "creator_reply", "رد المبدع"
    ADMIN = "admin", "قرار إدارة"


class MatchDecider(models.TextChoices):
    AUTO = "auto", "آلي"
    OWNER = "owner", "صاحب الحساب"
    ADMIN = "admin", "إدارة"


class ReconciliationMatch(TimestampedModel):
    """قرار مطابقة بين تحويل وارد وطلب سحب، بدرجة ثقة ومصدر قرار."""

    transfer = models.ForeignKey(
        IncomingTransfer, on_delete=models.PROTECT, related_name="matches"
    )
    request = models.ForeignKey(
        WithdrawalRequest, on_delete=models.PROTECT, related_name="matches"
    )
    method = models.CharField(max_length=30, choices=MatchMethod.choices)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    decided_by = models.CharField(max_length=10, choices=MatchDecider.choices)
    decided_at = models.DateTimeField()
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "reconciliation_matches"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0) & models.Q(confidence__lte=1),
                name="match_confidence_range",
            )
        ]
