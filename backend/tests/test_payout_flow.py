"""الدورة الكاملة من ضغطة السحب إلى الدفع، مع توازن الدفتر في كل خطوة."""
from decimal import Decimal

import pytest
from django.db.models import Sum

from apps.common.enums import Currency
from apps.common.errors import DomainError
from apps.ledger import services as ledger
from apps.ledger.models import LedgerAccountType, LedgerEntry
from apps.payouts.models import PayoutMethod, PayoutStatus
from apps.payouts.services import execute_payout
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db


@pytest.fixture
def method(db) -> PayoutMethod:
    return PayoutMethod.objects.create(name="إنستاباي يدوي", provider="manual")


def _ledger_is_balanced() -> bool:
    """كل قيد في الدفتر متوازن، والدفتر ككل متوازن."""
    per_txn = LedgerEntry.objects.values("txn_id", "currency").annotate(
        d=Sum("debit"), c=Sum("credit")
    )
    return all(row["d"] == row["c"] for row in per_txn)


def test_full_cycle_initiated_to_paid(request_initiated, creator, method):
    r = request_initiated
    for target in (S.TIKTOK_PROCESSING, S.TIKTOK_SENT):
        r = sm.transition(r, target)
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    r = sm.transition(r, S.APPROVED)

    payout = execute_payout(r, method=method, reference="IPN-99887", destination="0100000000")

    r.refresh_from_db()
    assert r.status == S.PAID
    assert r.paid_at is not None
    assert payout.status == PayoutStatus.EXECUTED
    assert payout.gross_amount == Decimal("4850.0000")
    assert payout.fee_amount == Decimal("242.5000")
    assert payout.net_amount == Decimal("4607.5000")

    # رصيد المبدع صفر بعد الدفع، والرسوم مسجَّلة، والصندوق خرج منه الصافي
    assert ledger.creator_balance(creator.id) == Decimal("0.0000")
    fees = ledger.get_or_create_account(type=LedgerAccountType.FEES, currency=Currency.EGP)
    cash = ledger.get_or_create_account(type=LedgerAccountType.CASH, currency=Currency.EGP)
    assert ledger.account_balance(fees) == Decimal("-242.5000")  # إيراد: دائن
    assert ledger.account_balance(cash) == Decimal("-4607.5000")  # خروج نقدي
    assert _ledger_is_balanced()


def test_payout_refused_before_approval(request_initiated, method):
    r = sm.transition(request_initiated, S.TIKTOK_SENT)
    with pytest.raises(DomainError):
        execute_payout(r, method=method, reference="IPN-1")
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    with pytest.raises(DomainError):
        execute_payout(r, method=method, reference="IPN-2")


def test_payout_requires_reference(request_initiated, method):
    r = sm.transition(request_initiated, S.TIKTOK_SENT)
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    r = sm.transition(r, S.APPROVED)
    with pytest.raises(DomainError):
        execute_payout(r, method=method, reference="")


def test_payout_refused_when_balance_insufficient(request_initiated, method):
    """لو وصل أقل مما هو مسجَّل، لا يُدفع الإجمالي القديم."""
    r = sm.transition(request_initiated, S.TIKTOK_SENT)
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("1000"))
    r = sm.transition(r, S.APPROVED)
    # المبلغ المقيَّد صار 1000 والرسوم 242.5 → الصافي موجب والدفع يمر
    payout = execute_payout(r, method=method, reference="IPN-3")
    assert payout.net_amount == Decimal("757.5000")
    assert _ledger_is_balanced()


def test_double_payout_is_impossible(request_initiated, method):
    r = sm.transition(request_initiated, S.TIKTOK_SENT)
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    r = sm.transition(r, S.APPROVED)
    execute_payout(r, method=method, reference="IPN-4")
    r.refresh_from_db()
    with pytest.raises(DomainError):
        execute_payout(r, method=method, reference="IPN-5")
