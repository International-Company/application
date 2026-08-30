"""إنشاء طلبات السحب واستقبال الإشارات وترجمتها إلى انتقالات حالة.

الإشارات تُحرّك الحالة ولا تُنشئ مالًا. المال يُقيَّد عند received_eg وحده،
وهو انتقال لا تصنعه إشارة من TikTok بل دليل وصول من الجانب المصري.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.common.errors import DomainError
from apps.creators.services import require_trusted_device
from apps.messaging.notifier import notify_creator
from apps.receiving import services as receiving

from . import state_machine as sm
from .models import (
    SignalKind,
    SignalSource,
    WithdrawalRequest,
    WithdrawalSignal,
    WithdrawalStatus,
)

# ما تعنيه كل إشارة من حيث الحالة المستهدفة
SIGNAL_TARGET = {
    SignalKind.PROCESSING: WithdrawalStatus.TIKTOK_PROCESSING,
    SignalKind.SENT: WithdrawalStatus.TIKTOK_SENT,
    SignalKind.REJECTED: WithdrawalStatus.TIKTOK_REJECTED,
    SignalKind.NOT_COMPLETED: WithdrawalStatus.CANCELLED,
}


class WithdrawalError(DomainError):
    """خطأ في إنشاء طلب سحب أو معالجته."""


def _signal_dedupe_key(creator_id, source: str, payload: dict) -> str:
    """بصمة الإشارة لمنع تكرار الرسالة نفسها من الجهاز."""
    raw = f"{creator_id}:{source}:{sorted(payload.items())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]


def _enforce_velocity(creator) -> None:
    """قواعد سرعة على مستوى المبدع — الحد اليومي والشهري لعدد الطلبات."""
    now = timezone.now()
    daily = WithdrawalRequest.objects.filter(
        creator=creator, initiated_at__gte=now - timedelta(days=1)
    ).count()
    if daily >= settings.MAX_WITHDRAWALS_PER_DAY:
        raise WithdrawalError("تجاوزت الحد اليومي لعدد طلبات السحب")

    monthly = WithdrawalRequest.objects.filter(
        creator=creator, initiated_at__gte=now - timedelta(days=30)
    ).count()
    if monthly >= settings.MAX_WITHDRAWALS_PER_MONTH:
        raise WithdrawalError("تجاوزت الحد الشهري لعدد طلبات السحب")


@transaction.atomic
def create_withdrawal(creator, device=None) -> WithdrawalRequest:
    """ضغطة «سحب». لا مبلغ ولا كتابة — المبلغ يأتي لاحقًا من إشارات TikTok."""
    require_trusted_device(creator, device)

    open_request = (
        WithdrawalRequest.objects.select_for_update()
        .filter(creator=creator, status=WithdrawalStatus.INITIATED)
        .first()
    )
    if open_request is not None:
        # الضغط المزدوج لا يُنشئ طلبًا ثانيًا بل يعيد الطلب القائم
        return open_request

    _enforce_velocity(creator)

    assignment = receiving.assign_receiving_account(creator)
    if assignment.autofilled_at is None:
        raise WithdrawalError("لم يكتمل تجهيز حساب الاستلام داخل TikTok بعد")

    request = WithdrawalRequest.objects.create(
        creator=creator,
        receiving_account=assignment.receiving_account,
        initiated_at=timezone.now(),
    )
    audit.record(
        action="withdrawal.initiated",
        entity="withdrawal_request",
        entity_id=request.id,
        actor_type=ActorType.CREATOR,
        actor_id=creator.id,
        after={"code": request.code},
    )
    return request


def _resolve_request(creator, code: str = "") -> WithdrawalRequest | None:
    """الطلب المقصود بالإشارة: بالرمز إن ذُكر، وإلا أحدث طلب مفتوح."""
    if code:
        return WithdrawalRequest.objects.filter(creator=creator, code=code).first()
    return (
        WithdrawalRequest.objects.filter(
            creator=creator,
            status__in=[WithdrawalStatus.INITIATED, WithdrawalStatus.TIKTOK_PROCESSING],
        )
        .order_by("-initiated_at")
        .first()
    )


@transaction.atomic
def ingest_signal(
    creator,
    *,
    source: str,
    kind: str,
    payload: dict | None = None,
    code: str = "",
    amount: str | None = None,
    currency: str = "",
    txn_id: str = "",
    occurred_at=None,
    package_sig_ok: bool = False,
) -> WithdrawalSignal:
    """تسجيل إشارة ومحاولة تحريك حالة الطلب بها."""
    payload = payload or {}
    dedupe_key = _signal_dedupe_key(creator.id, source, payload)
    existing = WithdrawalSignal.objects.filter(dedupe_key=dedupe_key).first()
    if existing is not None:
        return existing

    # مطالبة بتحويل متنازع عليه: تحسم صاحبه ولا تُنشئ مالًا بذاتها
    transfer_id = payload.get("transfer_id")
    if source == SignalSource.MANUAL and kind == SignalKind.RECEIVED and transfer_id:
        from apps.reconciliation import services as reconciliation

        reconciliation.claim_transfer(creator, str(transfer_id))

    request = _resolve_request(creator, code)
    signal = WithdrawalSignal.objects.create(
        request=request,
        creator=creator,
        source=source,
        kind=kind,
        raw_payload=payload,
        parsed_amount=amount,
        parsed_currency=currency,
        parsed_txn_id=txn_id,
        occurred_at=occurred_at,
        parsed_at=timezone.now(),
        package_sig_ok=package_sig_ok,
        dedupe_key=dedupe_key,
    )

    if request is None or not signal.is_trustworthy:
        # إشارة بلا طلب، أو إشعار بتوقيع حزمة غير متحقَّق منه: تُحفظ ولا تُصدَّق
        return signal

    _apply_signal(request, signal)
    return signal


def _apply_signal(request: WithdrawalRequest, signal: WithdrawalSignal) -> None:
    """ترجمة الإشارة إلى انتقال حالة إن كان مسموحًا."""
    target = SIGNAL_TARGET.get(signal.kind)
    if target is None or not sm.can_transition(request.status, target):
        return

    if signal.parsed_txn_id and not request.tiktok_txn_id:
        request.tiktok_txn_id = signal.parsed_txn_id
        request._via_state_machine = True
        request.save(update_fields=["tiktok_txn_id", "updated_at"])
        request._via_state_machine = False

    if signal.parsed_amount is not None and request.amount_usd is None:
        if (signal.parsed_currency or "USD").upper() == "USD":
            request.amount_usd = signal.parsed_amount
            request._via_state_machine = True
            request.save(update_fields=["amount_usd", "updated_at"])
            request._via_state_machine = False

    actor = sm.Actor(type=ActorType.CREATOR, id=request.creator_id)
    if signal.source == SignalSource.MANUAL:
        evidence = {"source": signal.source, "reason": "أفاد المبدع بعدم إتمام السحب"}
    else:
        evidence = {"source": signal.source, "signal_id": str(signal.id)}

    sm.transition(request, target, actor=actor, evidence=evidence)
    _notify_status_change(request, target)


def _notify_status_change(request: WithdrawalRequest, status: str) -> None:
    """إشعار المبدع بما يهمه فقط."""
    messages = {
        WithdrawalStatus.TIKTOK_PROCESSING: (
            "استلمنا طلبك",
            f"طلب السحب {request.code} قيد المعالجة لدى TikTok",
        ),
        WithdrawalStatus.TIKTOK_SENT: (
            "TikTok أرسل مبلغك",
            f"الطلب {request.code} في الطريق، جارٍ التشييك على وصوله",
        ),
        WithdrawalStatus.TIKTOK_REJECTED: (
            "تعذّر السحب",
            f"TikTok رفض الطلب {request.code}. تواصل معنا للمساعدة",
        ),
        WithdrawalStatus.RECEIVED_EG: (
            "وصل المبلغ",
            f"وصل مبلغ الطلب {request.code} وجارٍ تحويله إليك",
        ),
        WithdrawalStatus.PAID: ("تم الدفع", f"دُفع مبلغ الطلب {request.code}"),
    }
    if status not in messages:
        return
    title, body = messages[status]
    notify_creator(
        request.creator,
        title=title,
        body=body,
        request=request,
        data={"code": request.code, "status": status},
    )
