"""آلة حالات طلب السحب — المسار الوحيد لتغيير الحالة.

قاعدة مالية ثابتة: الانتقال إلى received_eg هو الوحيد الذي يُنشئ قيدًا دائنًا
لرصيد المبدع. أي حالة أخرى لا تلمس الدفتر.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType, Currency
from apps.common.errors import IllegalStateTransition
from apps.common.money import quantize
from apps.ledger import services as ledger
from apps.ledger.models import LedgerAccountType

from .models import WithdrawalRequest
from .models import WithdrawalStatus as S

logger = logging.getLogger("mobde3.withdrawals")

# الانتقالات المسموح بها فقط. ما ليس هنا مرفوض.
ALLOWED: dict[str, set[str]] = {
    S.INITIATED: {S.TIKTOK_PROCESSING, S.TIKTOK_SENT, S.TIKTOK_REJECTED, S.CANCELLED},
    S.TIKTOK_PROCESSING: {S.TIKTOK_SENT, S.TIKTOK_REJECTED, S.CANCELLED},
    S.TIKTOK_SENT: {S.RECEIVED_EG, S.NOT_RECEIVED},
    S.NOT_RECEIVED: {S.RECEIVED_EG, S.CANCELLED},
    S.RECEIVED_EG: {S.APPROVED},
    S.APPROVED: {S.PAID},
    S.PAID: set(),
    S.CANCELLED: set(),
    S.TIKTOK_REJECTED: set(),
}

# ختم الوقت المصاحب لكل حالة
TIMESTAMP_FIELD = {
    S.TIKTOK_PROCESSING: "processing_at",
    S.TIKTOK_SENT: "sent_at",
    S.RECEIVED_EG: "received_at",
    S.APPROVED: "approved_at",
    S.PAID: "paid_at",
}

CLOSING_STATUSES = {S.PAID, S.CANCELLED, S.TIKTOK_REJECTED}


@dataclass(frozen=True)
class Actor:
    """من نفّذ الانتقال."""

    type: str = ActorType.SYSTEM
    id: object = None
    label: str = ""


def can_transition(current: str, target: str) -> bool:
    """هل الانتقال مسموح؟"""
    return target in ALLOWED.get(current, set())


@transaction.atomic
def transition(
    request: WithdrawalRequest,
    target: str,
    *,
    actor: Actor | None = None,
    evidence: dict | None = None,
    amount_egp: Decimal | None = None,
) -> WithdrawalRequest:
    """تنفيذ انتقال حالة واحد بأثره المالي والتدقيقي."""
    actor = actor or Actor()
    request = WithdrawalRequest.objects.select_for_update().get(pk=request.pk)
    current = request.status

    if not can_transition(current, target):
        raise IllegalStateTransition(f"انتقال غير مسموح: {current} ← {target}")

    before = {"status": current}
    now = timezone.now()

    if target == S.RECEIVED_EG:
        _post_receipt_entry(request, amount_egp=amount_egp, now=now)

    request._via_state_machine = True
    request.status = target
    field = TIMESTAMP_FIELD.get(target)
    if field and getattr(request, field) is None:
        setattr(request, field, now)
    if target in CLOSING_STATUSES:
        request.closed_at = now
    if target == S.CANCELLED and evidence and evidence.get("reason"):
        request.cancel_reason = str(evidence["reason"])[:200]
    request.save()
    request._via_state_machine = False

    audit.record(
        action=f"withdrawal.{target}",
        entity="withdrawal_request",
        entity_id=request.id,
        actor_type=actor.type,
        actor_id=actor.id,
        actor_label=actor.label,
        before=before,
        after={"status": target, "evidence": evidence or {}},
    )
    _announce(request, target)
    return request


def _announce(request: WithdrawalRequest, target: str) -> None:
    """إبلاغ الجانب المصري والإدارة. فشل الرسالة لا يُبطل انتقالًا ماليًا."""
    from apps.messaging import services as messaging

    try:
        messaging.on_transition(request, target)
    except Exception:  # noqa: BLE001 — قناة الرسائل ليست جزءًا من صحة القيد
        logger.exception("تعذّر إبلاغ الجانب المصري بحالة %s للطلب %s", target, request.code)


def _post_receipt_entry(request: WithdrawalRequest, *, amount_egp: Decimal | None, now) -> None:
    """قيد وصول المال: مدين حساب الاستلام المصري / دائن رصيد المبدع."""
    expected = request.amount_egp or Decimal("0")
    amount = quantize(amount_egp if amount_egp is not None else expected)
    if amount <= 0:
        raise IllegalStateTransition("لا يمكن تسجيل الوصول بمبلغ صفر أو سالب")
    if request.receiving_account_id is None:
        raise IllegalStateTransition("الطلب بلا حساب استلام مخصص")

    receiving = ledger.get_or_create_account(
        type=LedgerAccountType.RECEIVING,
        ref_id=request.receiving_account_id,
        currency=Currency.EGP,
        name=str(request.receiving_account),
    )
    creator_balance = ledger.get_or_create_account(
        type=LedgerAccountType.CREATOR_BALANCE,
        ref_id=request.creator_id,
        currency=Currency.EGP,
        name=str(request.creator),
    )
    txn_id = ledger.post_transaction(
        [
            ledger.Line(account=receiving, debit=amount, memo=f"وصول {request.code}"),
            ledger.Line(account=creator_balance, credit=amount, memo=f"رصيد {request.code}"),
        ],
        request_id=request.id,
        memo=f"وصول تحويل الطلب {request.code}",
    )
    request.amount_egp = amount
    request.ledger_txn_id = txn_id
