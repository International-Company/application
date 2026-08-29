"""الدفتر: قيد مزدوج، إلحاق فقط، لا تعديل ولا حذف.

القاعدة المالية الحاكمة: لا يزيد رصيد مبدع إلا بقيد ناتج عن انتقال طلب إلى
received_eg، أي بعد إثبات وصول المال إلى حساب استلام مصري.
"""
from django.db import models

from apps.common.enums import Currency
from apps.common.errors import AppendOnlyViolation
from apps.common.models import TimestampedModel


class LedgerAccountType(models.TextChoices):
    RECEIVING = "receiving", "حساب استلام مصري"       # أصل
    CREATOR_BALANCE = "creator_balance", "رصيد مبدع"   # التزام على المنصة
    FEES = "fees", "رسوم"                              # إيراد
    CASH = "cash", "صندوق/سيولة"                       # أصل


class LedgerAccount(TimestampedModel):
    """حساب في الدفتر. ref_id يربطه بكيان المنصة (مبدع أو حساب استلام)."""

    code = models.CharField(max_length=60, unique=True)
    type = models.CharField(max_length=20, choices=LedgerAccountType.choices, db_index=True)
    ref_id = models.UUIDField(null=True, blank=True, db_index=True)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EGP)
    name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "ledger_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["type", "ref_id", "currency"],
                name="uniq_ledger_account_per_ref",
            )
        ]

    def __str__(self) -> str:
        return self.code


class LedgerEntry(TimestampedModel):
    """سطر قيد. كل سطر إما مدين أو دائن، ومجموع المدين = مجموع الدائن لكل txn_id."""

    txn_id = models.UUIDField(db_index=True)
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    debit = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    credit = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    request_id = models.UUIDField(null=True, blank=True, db_index=True)
    memo = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "ledger_entries"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                name="ledger_amounts_non_negative",
            ),
            models.CheckConstraint(
                # سطر واحد لا يكون مدينًا ودائنًا معًا، ولا يكون صفرًا
                condition=(
                    (models.Q(debit__gt=0) & models.Q(credit=0))
                    | (models.Q(credit__gt=0) & models.Q(debit=0))
                ),
                name="ledger_entry_single_side",
            ),
        ]
        indexes = [models.Index(fields=["account", "created_at"])]

    def save(self, *args, **kwargs):
        # حارس على مستوى التطبيق فوق حارس قاعدة البيانات
        if self.pk is not None and not self._state.adding:
            raise AppendOnlyViolation("لا يجوز تعديل سطر في الدفتر")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation("لا يجوز حذف سطر من الدفتر")
