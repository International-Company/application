"""آلة الحالات: كل انتقال مسموح، وكل انتقال ممنوع، والأثر المالي الوحيد."""
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.errors import IllegalStateTransition
from apps.ledger import services as ledger
from apps.ledger.models import LedgerEntry
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalRequest
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db

ALL_STATUSES = [s for s in S.values]


def _move(request, path):
    """تمرير الطلب عبر سلسلة حالات."""
    for target in path:
        request = sm.transition(request, target, amount_egp=request.amount_egp)
    return request


# --- الانتقالات المسموح بها ---------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        [S.TIKTOK_PROCESSING, S.TIKTOK_SENT, S.RECEIVED_EG, S.APPROVED, S.PAID],
        [S.TIKTOK_SENT, S.RECEIVED_EG, S.APPROVED, S.PAID],
        [S.TIKTOK_PROCESSING, S.TIKTOK_REJECTED],
        [S.TIKTOK_SENT, S.NOT_RECEIVED, S.RECEIVED_EG],
        [S.CANCELLED],
    ],
)
def test_allowed_paths(request_initiated, path):
    result = _move(request_initiated, path)
    assert result.status == path[-1]


def test_timestamps_are_stamped(request_initiated):
    r = _move(request_initiated, [S.TIKTOK_PROCESSING, S.TIKTOK_SENT, S.RECEIVED_EG])
    assert r.processing_at is not None
    assert r.sent_at is not None
    assert r.received_at is not None


def test_closing_status_sets_closed_at(request_initiated):
    r = _move(request_initiated, [S.TIKTOK_PROCESSING, S.TIKTOK_REJECTED])
    assert r.closed_at is not None


# --- الانتقالات الممنوعة ------------------------------------------------------

@pytest.mark.parametrize(
    "path,forbidden",
    [
        ([], S.RECEIVED_EG),        # لا وصول قبل الإرسال
        ([], S.APPROVED),           # لا اعتماد قبل الوصول
        ([], S.PAID),               # لا دفع من البداية
        ([S.TIKTOK_SENT], S.APPROVED),          # لا اعتماد قبل received_eg
        ([S.TIKTOK_SENT], S.PAID),              # لا دفع قبل received_eg
        ([S.TIKTOK_SENT], S.TIKTOK_PROCESSING), # لا رجوع للخلف
        ([S.TIKTOK_SENT, S.RECEIVED_EG], S.PAID),  # لا دفع دون اعتماد
        ([S.TIKTOK_SENT, S.RECEIVED_EG], S.CANCELLED),  # لا إلغاء بعد الوصول
        ([S.CANCELLED], S.TIKTOK_SENT),         # الملغى نهائي
        ([S.TIKTOK_PROCESSING, S.TIKTOK_REJECTED], S.RECEIVED_EG),  # المرفوض نهائي
    ],
)
def test_forbidden_transitions(request_initiated, path, forbidden):
    r = _move(request_initiated, path)
    with pytest.raises(IllegalStateTransition):
        sm.transition(r, forbidden, amount_egp=r.amount_egp)


def test_paid_is_terminal(request_initiated):
    r = _move(request_initiated, [S.TIKTOK_SENT, S.RECEIVED_EG, S.APPROVED, S.PAID])
    for target in ALL_STATUSES:
        with pytest.raises(IllegalStateTransition):
            sm.transition(r, target, amount_egp=r.amount_egp)


def test_direct_status_assignment_is_rejected(request_initiated):
    """لا يجوز تجاوز آلة الحالات بإسناد مباشر."""
    request_initiated.status = S.PAID
    with pytest.raises(IllegalStateTransition):
        request_initiated.save()


# --- القاعدة المالية ----------------------------------------------------------

def test_only_received_eg_creates_ledger_credit(request_initiated, creator):
    """لا قيد قبل received_eg، وقيد واحد عنده."""
    r = _move(request_initiated, [S.TIKTOK_PROCESSING, S.TIKTOK_SENT])
    assert LedgerEntry.objects.count() == 0
    assert ledger.creator_balance(creator.id) == Decimal("0.0000")

    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    assert LedgerEntry.objects.filter(txn_id=r.ledger_txn_id).count() == 2
    assert ledger.creator_balance(creator.id) == Decimal("4850.0000")

    sm.transition(r, S.APPROVED)
    assert LedgerEntry.objects.count() == 2  # الاعتماد لا يلمس الدفتر


def test_rejected_path_creates_no_ledger_entries(request_initiated, creator):
    _move(request_initiated, [S.TIKTOK_PROCESSING, S.TIKTOK_REJECTED])
    assert LedgerEntry.objects.count() == 0
    assert ledger.creator_balance(creator.id) == Decimal("0.0000")


def test_cancelled_path_creates_no_ledger_entries(request_initiated, creator):
    _move(request_initiated, [S.CANCELLED])
    assert LedgerEntry.objects.count() == 0


def test_received_with_zero_amount_is_rejected(request_initiated):
    r = _move(request_initiated, [S.TIKTOK_SENT])
    with pytest.raises(IllegalStateTransition):
        sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("0"))
    r.refresh_from_db()
    assert r.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_received_amount_overrides_expected_amount(request_initiated, creator):
    """المبلغ المقيَّد هو ما وصل فعلًا، لا ما كان متوقعًا."""
    r = _move(request_initiated, [S.TIKTOK_SENT])
    r = sm.transition(r, S.RECEIVED_EG, amount_egp=Decimal("4800"))
    assert r.amount_egp == Decimal("4800.0000")
    assert ledger.creator_balance(creator.id) == Decimal("4800.0000")


def test_every_transition_writes_audit_entry(request_initiated):
    from apps.audit.models import AuditLog

    _move(request_initiated, [S.TIKTOK_PROCESSING, S.TIKTOK_SENT, S.RECEIVED_EG])
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert actions == {
        "withdrawal.tiktok_processing",
        "withdrawal.tiktok_sent",
        "withdrawal.received_eg",
    }


# --- منع التكرار ---------------------------------------------------------------

def test_only_one_initiated_request_per_creator(request_initiated, creator, receiving_account):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WithdrawalRequest.objects.create(
                creator=creator,
                receiving_account=receiving_account,
                amount_usd=Decimal("50"),
                initiated_at=timezone.now(),
            )


def test_second_request_allowed_after_first_moves_on(request_initiated, creator, receiving_account):
    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    second = WithdrawalRequest.objects.create(
        creator=creator,
        receiving_account=receiving_account,
        amount_usd=Decimal("50"),
        initiated_at=timezone.now(),
    )
    assert second.status == S.INITIATED


def test_tiktok_txn_id_is_unique(request_initiated, other_creator, receiving_account):
    request_initiated.tiktok_txn_id = "TT-123456"
    request_initiated.save()
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            WithdrawalRequest.objects.create(
                creator=other_creator,
                receiving_account=receiving_account,
                amount_usd=Decimal("50"),
                initiated_at=timezone.now(),
                tiktok_txn_id="TT-123456",
            )


def test_null_tiktok_txn_id_does_not_collide(request_initiated, other_creator, receiving_account):
    second = WithdrawalRequest.objects.create(
        creator=other_creator,
        receiving_account=receiving_account,
        amount_usd=Decimal("50"),
        initiated_at=timezone.now(),
    )
    assert second.tiktok_txn_id is None
