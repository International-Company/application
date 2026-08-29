"""تنفيذ الدفع للمبدع وقيده في الدفتر."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.enums import ActorType, Currency
from apps.common.errors import DomainError
from apps.common.money import quantize
from apps.ledger import services as ledger
from apps.ledger.models import LedgerAccountType
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalRequest, WithdrawalStatus

from .models import PayoutMethod, PayoutStatus, PayoutTransaction


@transaction.atomic
def execute_payout(
    request: WithdrawalRequest,
    *,
    method: PayoutMethod,
    reference: str,
    executed_by=None,
    destination: str = "",
) -> PayoutTransaction:
    """تنفيذ دفعة: مدين رصيد المبدع بالإجمالي / دائن الرسوم + دائن الصندوق بالصافي."""
    if request.status != WithdrawalStatus.APPROVED:
        raise DomainError("لا يُدفع إلا لطلب معتمد")
    if not reference:
        raise DomainError("مرجع التحويل مطلوب")

    gross = quantize(request.amount_egp or Decimal("0"))
    fee = quantize(request.fee_egp or Decimal("0"))
    net = quantize(gross - fee)
    if net <= 0:
        raise DomainError("الصافي بعد الرسوم يجب أن يكون موجبًا")

    balance = ledger.creator_balance(request.creator_id, Currency.EGP)
    if balance < gross:
        raise DomainError("رصيد المبدع لا يكفي لهذه الدفعة")

    creator_account = ledger.get_or_create_account(
        type=LedgerAccountType.CREATOR_BALANCE, ref_id=request.creator_id, currency=Currency.EGP
    )
    fees_account = ledger.get_or_create_account(
        type=LedgerAccountType.FEES, currency=Currency.EGP, name="رسوم المنصة"
    )
    cash_account = ledger.get_or_create_account(
        type=LedgerAccountType.CASH, currency=Currency.EGP, name="الصندوق"
    )

    lines = [ledger.Line(account=creator_account, debit=gross, memo=f"دفع {request.code}")]
    if fee > 0:
        lines.append(ledger.Line(account=fees_account, credit=fee, memo=f"رسوم {request.code}"))
    lines.append(ledger.Line(account=cash_account, credit=net, memo=f"خروج نقدي {request.code}"))

    txn_id = ledger.post_transaction(lines, request_id=request.id, memo=f"دفع الطلب {request.code}")

    payout = PayoutTransaction.objects.create(
        request=request,
        method=method,
        gross_amount=gross,
        fee_amount=fee,
        net_amount=net,
        currency=Currency.EGP,
        destination=destination,
        reference=reference,
        status=PayoutStatus.EXECUTED,
        executed_by=executed_by,
        executed_at=timezone.now(),
        ledger_txn_id=txn_id,
    )

    request.net_amount_egp = net
    request._via_state_machine = True
    request.save(update_fields=["net_amount_egp", "updated_at"])
    request._via_state_machine = False

    sm.transition(
        request,
        WithdrawalStatus.PAID,
        actor=sm.Actor(
            type=ActorType.ADMIN if executed_by else ActorType.SYSTEM,
            id=getattr(executed_by, "id", None),
            label=getattr(executed_by, "email", ""),
        ),
        evidence={"reference": reference, "net_amount_egp": str(net)},
    )
    return payout
