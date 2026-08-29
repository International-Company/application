"""الدفع للمبدع بوسيلته المحلية."""
from django.db import models

from apps.common.enums import Currency
from apps.common.models import TimestampedModel
from apps.identity.models import AdminUser
from apps.withdrawals.models import WithdrawalRequest


class PayoutMethod(TimestampedModel):
    """وسيلة دفع. المرحلة الأولى يدوية؛ المزوّد يبقى خلف واجهة."""

    name = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=40, default="manual")
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    enabled = models.BooleanField(default=True)
    config_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "payout_methods"

    def __str__(self) -> str:
        return self.name


class PayoutStatus(models.TextChoices):
    PENDING = "pending", "بانتظار التنفيذ"
    EXECUTED = "executed", "نُفِّذ"
    FAILED = "failed", "فشل"


class PayoutTransaction(TimestampedModel):
    """أمر دفع للمبدع مقابل طلب سحب واحد."""

    request = models.OneToOneField(
        WithdrawalRequest, on_delete=models.PROTECT, related_name="payout"
    )
    method = models.ForeignKey(PayoutMethod, on_delete=models.PROTECT, related_name="transactions")
    gross_amount = models.DecimalField(max_digits=18, decimal_places=4)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    net_amount = models.DecimalField(max_digits=18, decimal_places=4)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    destination = models.CharField(max_length=150, blank=True, help_text="وسيلة استلام المبدع")
    reference = models.CharField(max_length=120, blank=True, help_text="مرجع التحويل المُسجَّل يدويًا")
    status = models.CharField(
        max_length=10, choices=PayoutStatus.choices, default=PayoutStatus.PENDING, db_index=True
    )
    executed_by = models.ForeignKey(
        AdminUser, on_delete=models.PROTECT, null=True, blank=True, related_name="executed_payouts"
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    ledger_txn_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "payout_transactions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(gross_amount__gt=0)
                & models.Q(net_amount__gt=0)
                & models.Q(fee_amount__gte=0),
                name="payout_amounts_valid",
            ),
            models.UniqueConstraint(
                fields=["reference"],
                condition=~models.Q(reference=""),
                name="uniq_payout_reference",
            ),
        ]
