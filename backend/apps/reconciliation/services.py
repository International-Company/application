"""مطابقة الوارد البنكي بطلبات السحب.

الترتيب كما في الوثيقة: عنوان استلام خاص أولًا، ثم الحساب والمبلغ والزمن.
مرشح واحد يعني مطابقة آلية؛ أكثر من مرشح يعني سؤالًا ثم قائمة الإدارة.
"""
import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType, Currency
from apps.common.errors import DomainError
from apps.common.money import quantize
from apps.ledger import services as ledger
from apps.ledger.models import LedgerAccountType
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalRequest, WithdrawalStatus

from .models import (
    CollectorDevice,
    IncomingTransfer,
    MatchDecider,
    MatchMethod,
    MatchStatus,
    ReconciliationMatch,
)

logger = logging.getLogger("mobde3.reconciliation")

# الحالات التي ما زال تحويلها متوقعًا
OPEN_STATUSES = [WithdrawalStatus.TIKTOK_SENT, WithdrawalStatus.NOT_RECEIVED]
# حالات قُيِّد فيها مبلغ تقديري وقد يحتاج تسوية عند وصول الرقم الحقيقي
SETTLED_STATUSES = [
    WithdrawalStatus.RECEIVED_EG,
    WithdrawalStatus.APPROVED,
    WithdrawalStatus.PAID,
]


class CollectorAuthError(DomainError):
    """فشل توثيق طلب تطبيق الجامع."""


@dataclass(frozen=True)
class Candidate:
    """طلب مرشّح لتحويل وارد، مع درجة ثقته."""

    request: WithdrawalRequest
    method: str
    confidence: Decimal
    expected_egp: Decimal


# --- توثيق تطبيق الجامع -----------------------------------------------------


def authenticate_collector(*, collector_id: str, timestamp: str, signature: str, body: bytes):
    """التحقق من توقيع الجهاز مع نافذة زمنية تمنع إعادة البث."""
    device = CollectorDevice.objects.filter(collector_id=collector_id, is_active=True).first()
    if device is None:
        raise CollectorAuthError("جهاز غير معروف أو موقوف")

    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise CollectorAuthError("طابع زمني غير صالح") from exc

    skew = abs(int(timezone.now().timestamp()) - sent_at)
    if skew > settings.COLLECTOR_MAX_SKEW_SECONDS:
        raise CollectorAuthError("الطابع الزمني خارج النافذة المسموحة")

    expected = hmac.new(
        device.secret_enc.encode("utf-8"),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature or ""):
        raise CollectorAuthError("توقيع غير صالح")

    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at", "updated_at"])
    return device


# --- المطابقة ---------------------------------------------------------------


def _expected_egp(request: WithdrawalRequest) -> Decimal | None:
    """المبلغ المتوقع بالجنيه وفق سعر الصرف المعتمد."""
    from apps.pricing import services as pricing

    if not request.amount_usd:
        return None
    rate = pricing.latest_fx_rate(at=request.sent_at)
    if rate is None:
        return None
    return quantize(Decimal(request.amount_usd) * rate.rate)


def _within_tolerance(actual: Decimal, expected: Decimal) -> bool:
    tolerance = Decimal(settings.RECONCILIATION_AMOUNT_TOLERANCE)
    return abs(actual - expected) <= expected * tolerance


def find_candidates(transfer: IncomingTransfer) -> list[Candidate]:
    """الطلبات المرشّحة لهذا التحويل، مرتبة بدرجة الثقة."""
    window_start = transfer.received_at - timedelta(days=settings.RECONCILIATION_MAX_DAYS)
    window_end = transfer.received_at

    open_requests = WithdrawalRequest.objects.filter(
        receiving_account_id=transfer.receiving_account_id,
        status__in=OPEN_STATUSES,
        sent_at__isnull=False,
        sent_at__gte=window_start,
        sent_at__lte=window_end,
    ).select_related("creator", "receiving_account")

    # عنوان استلام خاص بمبدع واحد يجعل صاحب التحويل قطعيًا
    exclusive = transfer.receiving_account.assignments.filter(active=True).count() == 1

    candidates: list[Candidate] = []
    for request in open_requests:
        expected = _expected_egp(request)
        if expected is None or expected <= 0:
            continue
        if not _within_tolerance(quantize(transfer.amount_egp), expected):
            continue
        if exclusive:
            candidates.append(
                Candidate(request, MatchMethod.UNIQUE_ADDRESS, Decimal("0.95"), expected)
            )
        else:
            candidates.append(
                Candidate(request, MatchMethod.ACCOUNT_AMOUNT_TIME, Decimal("0.90"), expected)
            )

    candidates.sort(key=lambda item: (-item.confidence, item.request.sent_at))
    return candidates


@transaction.atomic
def reconcile(transfer: IncomingTransfer) -> ReconciliationMatch | None:
    """محاولة مطابقة تحويل وارد. يعيد المطابقة إن تمت آليًا."""
    if transfer.matched_request_id is not None:
        return transfer.matches.first()

    candidates = find_candidates(transfer)

    if len(candidates) == 1:
        return _apply_match(
            transfer,
            candidates[0],
            decided_by=MatchDecider.AUTO,
            notes="مرشح وحيد ضمن الحساب والمبلغ والزمن",
        )

    if len(candidates) > 1:
        transfer.match_status = MatchStatus.AMBIGUOUS
        transfer.save(update_fields=["match_status", "updated_at"])
        _ask_candidates(transfer, candidates)
        return None

    transfer.match_status = MatchStatus.UNMATCHED
    transfer.save(update_fields=["match_status", "updated_at"])
    _settle_if_already_credited(transfer)
    return None


def _apply_match(
    transfer: IncomingTransfer,
    candidate: Candidate,
    *,
    decided_by: str,
    notes: str = "",
    actor_label: str = "",
) -> ReconciliationMatch:
    """ربط التحويل بالطلب، وتحويل الطلب إلى received_eg بالمبلغ الواصل فعلًا."""
    request = candidate.request
    amount = quantize(transfer.amount_egp)

    match = ReconciliationMatch.objects.create(
        transfer=transfer,
        request=request,
        method=candidate.method,
        confidence=candidate.confidence,
        decided_by=decided_by,
        decided_at=timezone.now(),
        notes=notes[:300],
    )
    transfer.matched_request = request
    transfer.matched_at = timezone.now()
    transfer.match_status = MatchStatus.MATCHED
    transfer.save(
        update_fields=["matched_request", "matched_at", "match_status", "updated_at"]
    )

    if sm.can_transition(request.status, WithdrawalStatus.RECEIVED_EG):
        from apps.pricing import services as pricing

        request.fee_egp = pricing.compute_fee(amount)
        request._via_state_machine = True
        request.save(update_fields=["fee_egp", "updated_at"])
        request._via_state_machine = False
        sm.transition(
            request,
            WithdrawalStatus.RECEIVED_EG,
            actor=sm.Actor(type=ActorType.SYSTEM, label=actor_label or "المطابقة الآلية"),
            amount_egp=amount,
            evidence={
                "source": transfer.source,
                "bank_ref": transfer.bank_ref,
                "amount_basis": "bank_record",
                "confidence": str(candidate.confidence),
            },
        )
    else:
        # الطلب قُيِّد سابقًا بمبلغ تقديري: يُسوّى الفرق بقيد تصحيحي
        _post_settlement(request, amount, transfer)

    _mark_assignment_confirmed(request)
    audit.record(
        action="reconciliation.matched",
        entity="incoming_transfer",
        entity_id=transfer.id,
        actor_type=ActorType.ADMIN if decided_by == MatchDecider.ADMIN else ActorType.SYSTEM,
        actor_label=actor_label,
        after={
            "request": request.code,
            "method": candidate.method,
            "confidence": str(candidate.confidence),
        },
    )
    return match


def _mark_assignment_confirmed(request: WithdrawalRequest) -> None:
    from apps.receiving import services as receiving

    assignment = receiving.active_assignment(request.creator)
    if assignment is not None:
        receiving.mark_confirmed(assignment)


def _post_settlement(
    request: WithdrawalRequest, actual: Decimal, transfer: IncomingTransfer
) -> None:
    """تسوية الفرق بين المبلغ المقيَّد تقديريًا والمبلغ الواصل فعلًا.

    الدفتر إلحاق فقط، فالتصحيح قيد جديد لا تعديل للقيد القديم.
    """
    credited = quantize(request.amount_egp or Decimal("0"))
    delta = quantize(actual - credited)
    if delta == 0:
        return

    receiving_account = ledger.get_or_create_account(
        type=LedgerAccountType.RECEIVING,
        ref_id=request.receiving_account_id,
        currency=Currency.EGP,
    )
    creator_account = ledger.get_or_create_account(
        type=LedgerAccountType.CREATOR_BALANCE,
        ref_id=request.creator_id,
        currency=Currency.EGP,
    )

    memo = f"تسوية {request.code} وفق كشف البنك"
    if delta > 0:
        lines = [
            ledger.Line(account=receiving_account, debit=delta, memo=memo),
            ledger.Line(account=creator_account, credit=delta, memo=memo),
        ]
    else:
        lines = [
            ledger.Line(account=creator_account, debit=-delta, memo=memo),
            ledger.Line(account=receiving_account, credit=-delta, memo=memo),
        ]

    ledger.post_transaction(lines, request_id=request.id, memo=memo)

    request.amount_egp = actual
    request._via_state_machine = True
    request.save(update_fields=["amount_egp", "updated_at"])
    request._via_state_machine = False

    audit.record(
        action="reconciliation.settled_difference",
        entity="withdrawal_request",
        entity_id=request.id,
        actor_type=ActorType.SYSTEM,
        before={"amount_egp": str(credited)},
        after={
            "amount_egp": str(actual),
            "delta": str(delta),
            "transfer": str(transfer.id),
            "status_at_settlement": request.status,
        },
    )


def _settle_if_already_credited(transfer: IncomingTransfer) -> None:
    """تحويل بلا مرشح مفتوح قد يخص طلبًا قُيِّد بتأكيد صاحب الحساب."""
    window_start = transfer.received_at - timedelta(days=settings.RECONCILIATION_MAX_DAYS)
    settled = list(
        WithdrawalRequest.objects.filter(
            receiving_account_id=transfer.receiving_account_id,
            status__in=SETTLED_STATUSES,
            received_at__gte=window_start,
            received_at__lte=transfer.received_at + timedelta(days=1),
            incoming_transfers__isnull=True,
        ).select_related("creator")
    )
    if len(settled) != 1:
        return

    request = settled[0]
    expected = _expected_egp(request) or quantize(request.amount_egp or Decimal("0"))
    if expected <= 0 or not _within_tolerance(quantize(transfer.amount_egp), expected):
        return

    transfer.matched_request = request
    transfer.matched_at = timezone.now()
    transfer.match_status = MatchStatus.MATCHED
    transfer.save(
        update_fields=["matched_request", "matched_at", "match_status", "updated_at"]
    )
    ReconciliationMatch.objects.create(
        transfer=transfer,
        request=request,
        method=MatchMethod.ACCOUNT_AMOUNT_TIME,
        confidence=Decimal("0.90"),
        decided_by=MatchDecider.AUTO,
        decided_at=timezone.now(),
        notes="تسوية قيد سابق أُنشئ بتأكيد صاحب الحساب",
    )
    _post_settlement(request, quantize(transfer.amount_egp), transfer)


def _ask_candidates(transfer: IncomingTransfer, candidates: list[Candidate]) -> None:
    """سؤال كل مرشح، وتنبيه الإدارة بأن هناك تعارضًا."""
    from apps.messaging.notifier import notify_creator

    for candidate in candidates:
        notify_creator(
            candidate.request.creator,
            title="تأكيد سحب",
            body=(
                f"هل سحبت {candidate.request.amount_usd}$ في الطلب "
                f"{candidate.request.code}؟"
            ),
            request=candidate.request,
            data={
                "action": "claim_transfer",
                "transfer_id": str(transfer.id),
                "code": candidate.request.code,
            },
        )

    audit.record(
        action="reconciliation.ambiguous",
        entity="incoming_transfer",
        entity_id=transfer.id,
        actor_type=ActorType.SYSTEM,
        after={
            "amount_egp": str(transfer.amount_egp),
            "candidates": [candidate.request.code for candidate in candidates],
        },
    )


@transaction.atomic
def claim_transfer(creator, transfer_id: str) -> ReconciliationMatch | None:
    """مطالبة مبدع بتحويل متنازع عليه.

    المطالبة لا تُنشئ مالًا بذاتها: هي تحسم أيّ المرشحين صاحب التحويل، ولا
    تُقبل إلا إذا كان المبدع مرشحًا أصلًا وكان وحده من طالب به.
    """
    transfer = (
        IncomingTransfer.objects.select_for_update()
        .filter(pk=transfer_id, match_status=MatchStatus.AMBIGUOUS)
        .first()
    )
    if transfer is None:
        return None

    candidates = find_candidates(transfer)
    mine = [item for item in candidates if item.request.creator_id == creator.id]
    if len(mine) != 1:
        return None

    others_claimed = ReconciliationMatch.objects.filter(transfer=transfer).exists()
    if others_claimed:
        return None

    return _apply_match(
        transfer,
        mine[0],
        decided_by=MatchDecider.CREATOR,
        notes="حسم بمطالبة المبدع بعد تعارض",
    )


@transaction.atomic
def match_manually(
    transfer: IncomingTransfer, request: WithdrawalRequest, *, admin
) -> ReconciliationMatch:
    """مطابقة يدوية من الإدارة عند تعذّر الآلية."""
    if transfer.matched_request_id is not None:
        raise DomainError("التحويل مطابَق بالفعل")
    if request.receiving_account_id != transfer.receiving_account_id:
        raise DomainError("الطلب لا يخص حساب الاستلام نفسه")

    expected = _expected_egp(request) or quantize(transfer.amount_egp)
    candidate = Candidate(request, MatchMethod.ADMIN, Decimal("1.000"), expected)
    return _apply_match(
        transfer,
        candidate,
        decided_by=MatchDecider.ADMIN,
        notes="مطابقة يدوية",
        actor_label=getattr(admin, "email", ""),
    )


@transaction.atomic
def record_incoming(
    *,
    receiving_account,
    amount_egp: Decimal,
    received_at,
    bank_ref: str = "",
    sender_hint: str = "",
    source: str,
    raw_payload: dict | None = None,
    dedupe_key: str = "",
    collector=None,
) -> tuple[IncomingTransfer, bool]:
    """تسجيل تحويل وارد ومحاولة مطابقته. يعيد (التحويل، هل هو جديد)."""
    if dedupe_key:
        existing = IncomingTransfer.objects.filter(dedupe_key=dedupe_key).first()
        if existing is not None:
            return existing, False

    transfer = IncomingTransfer.objects.create(
        receiving_account=receiving_account,
        amount_egp=quantize(amount_egp),
        received_at=received_at,
        bank_ref=bank_ref,
        sender_hint=sender_hint,
        source=source,
        raw_payload=raw_payload or {},
        dedupe_key=dedupe_key,
        collector=collector,
    )
    reconcile(transfer)
    transfer.refresh_from_db()
    return transfer, True
