"""المطابقة الآلية وتطبيق الجامع.

معيار القبول للمرحلة: مطابقة آلية لا تقل عن ٩٠٪ في بيانات اختبار واقعية.
"""
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.creators.models import Creator
from apps.ledger import services as ledger
from apps.ledger.models import LedgerEntry
from apps.receiving.models import CreatorReceivingAssignment, ReceivingAccount
from apps.reconciliation import services as reconciliation
from apps.reconciliation.models import (
    CollectorDevice,
    IncomingTransfer,
    MatchStatus,
    ReconciliationMatch,
    TransferSource,
)
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalRequest
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/v1/reconciliation/incoming"
SECRET = "collector-secret-value"
RATE = Decimal("48.500000")


@pytest.fixture
def collector(db) -> CollectorDevice:
    return CollectorDevice.objects.create(
        name="هاتف الشركة", collector_id="col-1", secret_enc=SECRET
    )


@pytest.fixture
def sent_request(request_initiated, fx_rate) -> WithdrawalRequest:
    """طلب أرسله TikTok بمئة دولار وينتظر وصوله."""
    return sm.transition(request_initiated, S.TIKTOK_SENT)


def post_incoming(payload: dict, *, secret=SECRET, collector_id="col-1", skew=0):
    body = json.dumps(payload, default=str).encode()
    timestamp = str(int(timezone.now().timestamp()) + skew)
    signature = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return Client().post(
        ENDPOINT,
        data=body,
        content_type="application/json",
        HTTP_X_COLLECTOR_ID=collector_id,
        HTTP_X_TIMESTAMP=timestamp,
        HTTP_X_SIGNATURE=signature,
    )


def transfer_payload(account, amount, *, when=None, key="sms-1", ref="BNK-1"):
    return {
        "account_identifier": account.identifier,
        "amount_egp": str(amount),
        "received_at": (when or timezone.now()).isoformat(),
        "bank_ref": ref,
        "sender_hint": "TIKTOK",
        "source": TransferSource.SMS,
        "dedupe_key": key,
    }


# --- توثيق تطبيق الجامع -----------------------------------------------------

def test_unsigned_request_is_rejected(collector, receiving_account):
    response = Client().post(
        ENDPOINT,
        data=json.dumps(transfer_payload(receiving_account, "100")),
        content_type="application/json",
    )
    assert response.status_code == 403
    assert IncomingTransfer.objects.count() == 0


def test_wrong_secret_is_rejected(collector, receiving_account):
    response = post_incoming(transfer_payload(receiving_account, "100"), secret="wrong")
    assert response.status_code == 403
    assert IncomingTransfer.objects.count() == 0


def test_unknown_device_is_rejected(collector, receiving_account):
    response = post_incoming(transfer_payload(receiving_account, "100"), collector_id="ghost")
    assert response.status_code == 403


def test_disabled_device_is_rejected(collector, receiving_account):
    collector.is_active = False
    collector.save()
    assert post_incoming(transfer_payload(receiving_account, "100")).status_code == 403


def test_stale_timestamp_is_rejected(collector, receiving_account):
    """إعادة بث طلب قديم موقّع لا تُقبل."""
    response = post_incoming(transfer_payload(receiving_account, "100"), skew=-3600)
    assert response.status_code == 403


def test_valid_request_is_stored_and_device_seen(collector, receiving_account):
    response = post_incoming(transfer_payload(receiving_account, "100"))
    assert response.status_code == 201
    assert IncomingTransfer.objects.count() == 1
    collector.refresh_from_db()
    assert collector.last_seen_at is not None


def test_duplicate_delivery_is_ignored(collector, receiving_account):
    payload = transfer_payload(receiving_account, "100")
    assert post_incoming(payload).status_code == 201
    second = post_incoming(payload)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert IncomingTransfer.objects.count() == 1


def test_unknown_account_does_not_create_anything(collector, receiving_account):
    payload = transfer_payload(receiving_account, "100")
    payload["account_identifier"] = "nobody@instapay"
    response = post_incoming(payload)
    assert response.json()["error"]["code"] == "unknown_account"
    assert IncomingTransfer.objects.count() == 0


# --- المطابقة الآلية --------------------------------------------------------

def test_exact_amount_matches_and_credits(collector, sent_request, receiving_account):
    response = post_incoming(transfer_payload(receiving_account, "4850.0000"))
    assert response.json()["match_status"] == MatchStatus.MATCHED
    assert response.json()["matched_request"] == sent_request.code

    sent_request.refresh_from_db()
    assert sent_request.status == S.RECEIVED_EG
    assert sent_request.amount_egp == Decimal("4850.0000")
    assert ledger.creator_balance(sent_request.creator_id) == Decimal("4850.0000")


def test_amount_within_tolerance_matches(collector, sent_request, receiving_account):
    """٤٨٥٠ ± ٣٪ يقع ضمنها ٤٧٥٠."""
    post_incoming(transfer_payload(receiving_account, "4750.0000"))
    sent_request.refresh_from_db()
    assert sent_request.status == S.RECEIVED_EG
    # المقيَّد هو الواصل فعلًا لا المتوقع
    assert sent_request.amount_egp == Decimal("4750.0000")


def test_amount_outside_tolerance_does_not_match(collector, sent_request, receiving_account):
    post_incoming(transfer_payload(receiving_account, "3000.0000"))
    sent_request.refresh_from_db()
    assert sent_request.status == S.TIKTOK_SENT
    assert IncomingTransfer.objects.get().match_status == MatchStatus.UNMATCHED
    assert LedgerEntry.objects.count() == 0


def test_transfer_outside_time_window_does_not_match(collector, sent_request, receiving_account):
    old = timezone.now() - timedelta(days=10)
    WithdrawalRequest.objects.filter(pk=sent_request.pk).update(sent_at=old)
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    sent_request.refresh_from_db()
    assert sent_request.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_transfer_to_another_account_does_not_match(
    collector, sent_request, owner, receiving_account
):
    other = ReceivingAccount.objects.create(
        owner=owner, type="ipa", identifier="other@instapay", max_creators=1
    )
    post_incoming(transfer_payload(other, "4850.0000"))
    sent_request.refresh_from_db()
    assert sent_request.status == S.TIKTOK_SENT


def test_matching_confirms_the_assignment(collector, sent_request, receiving_account, assignment):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    assignment.refresh_from_db()
    assert assignment.confirmed_at is not None


# --- التعارض ----------------------------------------------------------------

@pytest.fixture
def two_candidates(db, receiving_account, creator, other_creator, fx_rate, assignment):
    """مبدعان على حساب استلام واحد، كلاهما بطلب مرسَل بنفس المبلغ."""
    CreatorReceivingAssignment.objects.create(
        creator=other_creator, receiving_account=receiving_account, assigned_at=timezone.now()
    )
    requests = []
    for owner_creator in (creator, other_creator):
        request = WithdrawalRequest.objects.create(
            creator=owner_creator,
            receiving_account=receiving_account,
            amount_usd=Decimal("100"),
            initiated_at=timezone.now(),
        )
        requests.append(sm.transition(request, S.TIKTOK_SENT))
    return requests


def test_two_candidates_produce_no_automatic_match(collector, two_candidates, receiving_account):
    response = post_incoming(transfer_payload(receiving_account, "4850.0000"))
    assert response.json()["match_status"] == MatchStatus.AMBIGUOUS
    for request in two_candidates:
        request.refresh_from_db()
        assert request.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_ambiguity_is_written_to_the_audit_log(collector, two_candidates, receiving_account):
    from apps.audit.models import AuditLog

    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    entry = AuditLog.objects.filter(action="reconciliation.ambiguous").first()
    assert entry is not None
    assert len(entry.after_json["candidates"]) == 2


def test_creator_claim_resolves_the_conflict(collector, two_candidates, receiving_account):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    transfer = IncomingTransfer.objects.get()

    claimant = two_candidates[0]
    reconciliation.claim_transfer(claimant.creator, str(transfer.id))

    claimant.refresh_from_db()
    other = two_candidates[1]
    other.refresh_from_db()
    assert claimant.status == S.RECEIVED_EG
    assert other.status == S.TIKTOK_SENT
    assert ledger.creator_balance(claimant.creator_id) == Decimal("4850.0000")
    assert ledger.creator_balance(other.creator_id) == Decimal("0.0000")


def test_a_stranger_cannot_claim_a_transfer(collector, two_candidates, receiving_account):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    transfer = IncomingTransfer.objects.get()
    stranger = Creator.objects.create(phone="+201777777777", display_name="غريب")

    assert reconciliation.claim_transfer(stranger, str(transfer.id)) is None
    assert LedgerEntry.objects.count() == 0


def test_second_claim_after_resolution_is_refused(collector, two_candidates, receiving_account):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    transfer = IncomingTransfer.objects.get()
    reconciliation.claim_transfer(two_candidates[0].creator, str(transfer.id))

    assert reconciliation.claim_transfer(two_candidates[1].creator, str(transfer.id)) is None
    assert ReconciliationMatch.objects.count() == 1


# --- تسوية المبلغ التقديري --------------------------------------------------

def test_bank_record_settles_an_estimated_credit(collector, sent_request, receiving_account):
    """قُيِّد تقديريًا بتأكيد صاحب الحساب، ثم وصل الرقم الحقيقي مختلفًا."""
    sm.transition(sent_request, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    assert ledger.creator_balance(sent_request.creator_id) == Decimal("4850.0000")

    post_incoming(transfer_payload(receiving_account, "4800.0000"))

    sent_request.refresh_from_db()
    assert sent_request.amount_egp == Decimal("4800.0000")
    assert ledger.creator_balance(sent_request.creator_id) == Decimal("4800.0000")

    from apps.audit.models import AuditLog

    entry = AuditLog.objects.filter(action="reconciliation.settled_difference").first()
    assert entry is not None
    assert entry.after_json["delta"] == "-50.0000"


def test_settlement_never_edits_the_original_entry(collector, sent_request, receiving_account):
    sm.transition(sent_request, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    original_ids = set(LedgerEntry.objects.values_list("id", flat=True))

    post_incoming(transfer_payload(receiving_account, "4900.0000"))

    after = LedgerEntry.objects.filter(id__in=original_ids)
    assert after.count() == len(original_ids)
    assert all(entry.debit + entry.credit == Decimal("4850.0000") for entry in after)
    assert ledger.creator_balance(sent_request.creator_id) == Decimal("4900.0000")


def test_every_transaction_stays_balanced_after_settlement(
    collector, sent_request, receiving_account
):
    from django.db.models import Sum

    sm.transition(sent_request, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    post_incoming(transfer_payload(receiving_account, "4790.0000"))

    rows = LedgerEntry.objects.values("txn_id", "currency").annotate(
        d=Sum("debit"), c=Sum("credit")
    )
    assert all(row["d"] == row["c"] for row in rows)


# --- المطابقة اليدوية من الإدارة --------------------------------------------

def test_admin_can_match_manually(collector, two_candidates, receiving_account, admin_client):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    transfer = IncomingTransfer.objects.get()

    response = admin_client.post(
        reverse("api_v1:api_admin:transfer-match", args=[transfer.id]),
        {"code": two_candidates[1].code},
        format="json",
    )
    assert response.status_code == 201
    two_candidates[1].refresh_from_db()
    assert two_candidates[1].status == S.RECEIVED_EG


def test_admin_sees_candidates(collector, two_candidates, receiving_account, admin_client):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    transfer = IncomingTransfer.objects.get()
    response = admin_client.get(
        reverse("api_v1:api_admin:transfer-candidates", args=[transfer.id])
    )
    assert len(response.data) == 2


def test_admin_transfer_list_counts_by_status(
    collector, sent_request, receiving_account, admin_client
):
    post_incoming(transfer_payload(receiving_account, "4850.0000"))
    response = admin_client.get(reverse("api_v1:api_admin:transfers"))
    assert response.data["counts"][MatchStatus.MATCHED] == 1


# --- معيار القبول: نسبة المطابقة الآلية -------------------------------------

def test_auto_match_rate_meets_the_acceptance_bar(collector, owner, fx_rate):
    """بيانات اختبار واقعية: عشرون تحويلًا، والمطلوب مطابقة آلية ≥ ٩٠٪."""
    total = 20
    matched = 0

    for index in range(total):
        creator = Creator.objects.create(
            phone=f"+2010000{index:05d}", display_name=f"مبدع {index}"
        )
        account = ReceivingAccount.objects.create(
            owner=owner,
            type="ipa",
            identifier=f"acc{index}@instapay",
            max_creators=1,
        )
        CreatorReceivingAssignment.objects.create(
            creator=creator, receiving_account=account, assigned_at=timezone.now()
        )
        amount_usd = Decimal("50") + index
        request = WithdrawalRequest.objects.create(
            creator=creator,
            receiving_account=account,
            amount_usd=amount_usd,
            initiated_at=timezone.now(),
        )
        sm.transition(request, S.TIKTOK_SENT)

        # فروق واقعية في المبلغ والزمن: رسوم بنك بسيطة ووصول بعد يوم أو يومين
        drift = Decimal("1") - (Decimal(index % 3) / Decimal("200"))
        amount_egp = (amount_usd * RATE * drift).quantize(Decimal("0.0001"))
        arrival = timezone.now() + timedelta(days=1 + (index % 3))

        post_incoming(
            transfer_payload(account, amount_egp, when=arrival, key=f"sms-{index}")
        )
        request.refresh_from_db()
        matched += int(request.status == S.RECEIVED_EG)

    rate = matched / total
    assert rate >= 0.9, f"نسبة المطابقة الآلية {rate:.0%} أقل من المطلوب"


# --- توافق التوقيع مع تطبيق الجامع ------------------------------------------

def test_signature_scheme_matches_the_collector_app(collector, receiving_account):
    """التوقيع كما يبنيه ApiClient.kt حرفًا بحرف: HMAC-SHA256 على «الطابع.الجسم»."""
    payload = json.dumps(transfer_payload(receiving_account, "4850.0000"))
    timestamp = str(int(timezone.now().timestamp()))

    # نفس ما يفعله الكوتلن: mac.doFinal("$timestamp.$payload") ثم %02x لكل بايت
    message = f"{timestamp}.{payload}"
    signature = hmac.new(
        SECRET.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    device = reconciliation.authenticate_collector(
        collector_id="col-1",
        timestamp=timestamp,
        signature=signature,
        body=payload.encode("utf-8"),
    )
    assert device.collector_id == "col-1"
