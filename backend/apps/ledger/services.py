"""الخدمة الوحيدة المسموح لها بالكتابة في الدفتر."""
import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.common.enums import Currency
from apps.common.errors import UnbalancedTransaction
from apps.common.money import quantize

from .models import LedgerAccount, LedgerAccountType, LedgerEntry


@dataclass(frozen=True)
class Line:
    """سطر مقترح في قيد: حساب ومبلغ مدين أو دائن."""

    account: LedgerAccount
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    memo: str = ""


@transaction.atomic
def post_transaction(lines: list[Line], *, request_id=None, memo: str = "") -> uuid.UUID:
    """تسجيل قيد متوازن. يرفض أي قيد غير متوازن قبل لمس قاعدة البيانات."""
    if len(lines) < 2:
        raise UnbalancedTransaction("القيد يحتاج سطرين على الأقل")

    totals: dict[str, list[Decimal]] = {}
    for line in lines:
        debit, credit = quantize(line.debit), quantize(line.credit)
        if debit < 0 or credit < 0:
            raise UnbalancedTransaction("لا تُقبل المبالغ السالبة")
        if (debit > 0) == (credit > 0):
            raise UnbalancedTransaction("كل سطر إما مدين أو دائن، وليس كليهما ولا صفرًا")
        bucket = totals.setdefault(line.account.currency, [Decimal("0"), Decimal("0")])
        bucket[0] += debit
        bucket[1] += credit

    for currency, (debits, credits) in totals.items():
        if debits != credits:
            raise UnbalancedTransaction(
                f"القيد غير متوازن بعملة {currency}: مدين {debits} مقابل دائن {credits}"
            )

    txn_id = uuid.uuid4()
    LedgerEntry.objects.bulk_create(
        [
            LedgerEntry(
                txn_id=txn_id,
                account=line.account,
                debit=quantize(line.debit),
                credit=quantize(line.credit),
                currency=line.account.currency,
                request_id=request_id,
                memo=line.memo or memo,
            )
            for line in lines
        ]
    )
    return txn_id


def get_or_create_account(
    *, type: str, ref_id=None, currency: str = Currency.EGP, name: str = ""
) -> LedgerAccount:
    """جلب حساب دفتر أو إنشاؤه — الرمز مشتق من النوع والمرجع."""
    code = f"{type}:{ref_id}" if ref_id else f"{type}:general"
    account, _ = LedgerAccount.objects.get_or_create(
        code=code,
        defaults={"type": type, "ref_id": ref_id, "currency": currency, "name": name},
    )
    return account


def creator_balance(creator_id, currency: str = Currency.EGP) -> Decimal:
    """رصيد المبدع = مجموع الدائن ناقص المدين على حسابه (حساب التزام)."""
    agg = LedgerEntry.objects.filter(
        account__type=LedgerAccountType.CREATOR_BALANCE,
        account__ref_id=creator_id,
        currency=currency,
    ).aggregate(d=Sum("debit"), c=Sum("credit"))
    return quantize((agg["c"] or Decimal("0")) - (agg["d"] or Decimal("0")))


def account_balance(account: LedgerAccount) -> Decimal:
    """رصيد حساب بمنطق المدين ناقص الدائن (يصلح للأصول)."""
    agg = account.entries.aggregate(d=Sum("debit"), c=Sum("credit"))
    return quantize((agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0")))
