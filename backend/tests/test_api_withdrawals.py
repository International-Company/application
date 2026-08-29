"""رحلة السحب عبر الـ API: التجهيز، الضغطة، الإشارات، المهل الزمنية."""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.creators.models import Creator, IntegrityVerdict
from apps.creators.sms import ConsoleSmsSender
from apps.ledger.models import LedgerEntry
from apps.receiving.models import CreatorReceivingAssignment
from apps.withdrawals.models import WithdrawalRequest, WithdrawalSignal
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db

DEVICE = "device-abc-123"
PHONE = "+201234567890"


@pytest.fixture(autouse=True)
def captured_sms(monkeypatch):
    sender = ConsoleSmsSender()
    monkeypatch.setattr("apps.creators.services.get_sms_sender", lambda: sender)
    return sender


@pytest.fixture
def client(captured_sms) -> APIClient:
    """عميل مصادَق عليه لمبدع موثّق الهاتف."""
    api = APIClient()
    preauth = api.post(
        reverse("api_v1:tiktok-exchange"), {"code": "c", "device_id": DEVICE}, format="json"
    ).data["preauth_token"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {preauth}")
    api.post(reverse("api_v1:phone-verify"), {"phone": PHONE}, format="json")
    otp = captured_sms.sent[-1][1].split(":")[-1].strip()
    session = api.post(
        reverse("api_v1:phone-verify"),
        {"phone": PHONE, "code": otp, "device_id": DEVICE},
        format="json",
    ).data["session"]
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
    # الخطوة التي يقوم بها التطبيق بعد الدخول: تسجيل الجهاز برمز سلامته
    api.post(
        reverse("api_v1:creator-devices"),
        {"device_id": DEVICE, "integrity_token": "play-integrity-token", "fcm_token": "fcm-1"},
        format="json",
    )
    return api


@pytest.fixture
def api_creator(client) -> Creator:
    return Creator.objects.get(phone=PHONE)


@pytest.fixture
def ready(client, api_creator, receiving_account):
    """مبدع أكمل التجهيز: خُصص له حساب وعُبّئ داخل TikTok."""
    client.get(reverse("api_v1:autofill-dataset"))
    client.post(reverse("api_v1:setup-complete"), {}, format="json")
    return api_creator


def signal(client, kind, **extra):
    body = {"source": "notification", "kind": kind, "package_sig_ok": True,
            "package_name": "com.zhiliaoapp.musically", "payload": {"n": kind, **extra}}
    body.update({k: v for k, v in extra.items() if k != "payload"})
    return client.post(reverse("api_v1:withdrawal-signals"), body, format="json")


# --- التجهيز ---------------------------------------------------------------

def test_autofill_dataset_assigns_account(client, api_creator, receiving_account):
    response = client.get(reverse("api_v1:autofill-dataset"))
    assert response.status_code == 200
    assert response.data["identifier"] == receiving_account.identifier
    assert CreatorReceivingAssignment.objects.filter(creator=api_creator, active=True).exists()


def test_autofill_returns_same_account_every_time(client, receiving_account):
    first = client.get(reverse("api_v1:autofill-dataset")).data
    second = client.get(reverse("api_v1:autofill-dataset")).data
    assert first == second
    assert CreatorReceivingAssignment.objects.count() == 1


def test_autofill_fails_gracefully_without_capacity(client):
    response = client.get(reverse("api_v1:autofill-dataset"))
    assert response.status_code == 503
    assert response.data["error"]["code"] == "no_capacity"


def test_setup_complete_marks_creator_ready(client, api_creator, receiving_account):
    client.get(reverse("api_v1:autofill-dataset"))
    response = client.post(reverse("api_v1:setup-complete"), {}, format="json")
    assert response.status_code == 200
    api_creator.refresh_from_db()
    assert api_creator.status == "setup_completed"
    assert CreatorReceivingAssignment.objects.get().autofilled_at is not None


# --- ضغطة السحب -----------------------------------------------------------

def test_withdrawal_requires_completed_setup(client, receiving_account):
    client.get(reverse("api_v1:autofill-dataset"))
    response = client.post(reverse("api_v1:withdrawals"), {}, format="json")
    assert response.status_code == 400
    assert WithdrawalRequest.objects.count() == 0


def test_withdrawal_press_creates_request_without_any_input(client, ready):
    response = client.post(reverse("api_v1:withdrawals"), {}, format="json")
    assert response.status_code == 201
    body = response.data["withdrawal"]
    assert body["status"] == S.INITIATED
    assert body["code"].startswith("WD-")
    # لا مبلغ ولا مرجع: المبدع لم يكتب حرفًا
    assert body["amount_usd"] is None
    assert response.data["next_step"] == "open_tiktok_balance"


def test_double_press_returns_same_request(client, ready):
    first = client.post(reverse("api_v1:withdrawals"), {}, format="json").data["withdrawal"]
    second = client.post(reverse("api_v1:withdrawals"), {}, format="json").data["withdrawal"]
    assert first["code"] == second["code"]
    assert WithdrawalRequest.objects.count() == 1


def test_untrusted_device_cannot_withdraw(client, ready):
    ready.devices.update(integrity_verdict=IntegrityVerdict.UNTRUSTED)
    response = client.post(reverse("api_v1:withdrawals"), {}, format="json")
    assert response.status_code == 400
    assert WithdrawalRequest.objects.count() == 0


def test_daily_velocity_limit_is_enforced(client, ready, settings):
    settings.MAX_WITHDRAWALS_PER_DAY = 2
    for _ in range(2):
        code = client.post(reverse("api_v1:withdrawals"), {}, format="json").data["withdrawal"][
            "code"
        ]
        WithdrawalRequest.objects.filter(code=code).update(status=S.TIKTOK_PROCESSING)
    response = client.post(reverse("api_v1:withdrawals"), {}, format="json")
    assert response.status_code == 400
    assert WithdrawalRequest.objects.count() == 2


# --- الإشارات -------------------------------------------------------------

def test_signal_moves_request_to_processing(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    response = signal(client, "processing")
    assert response.status_code == 202
    assert response.data["accepted"] is True
    assert WithdrawalRequest.objects.get().status == S.TIKTOK_PROCESSING


def test_signal_without_valid_package_signature_is_stored_but_ignored(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    response = client.post(
        reverse("api_v1:withdrawal-signals"),
        {"source": "notification", "kind": "sent", "package_sig_ok": False, "payload": {"x": 1}},
        format="json",
    )
    assert response.status_code == 202
    assert response.data["accepted"] is False
    assert WithdrawalSignal.objects.count() == 1
    assert WithdrawalRequest.objects.get().status == S.INITIATED


def test_signal_from_foreign_package_is_ignored(client, ready):
    """تطبيق مزيّف يدّعي أنه TikTok لا يُصدَّق."""
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    response = client.post(
        reverse("api_v1:withdrawal-signals"),
        {
            "source": "notification",
            "kind": "sent",
            "package_sig_ok": True,
            "package_name": "com.evil.fake",
            "payload": {"x": 2},
        },
        format="json",
    )
    assert response.data["accepted"] is False
    assert WithdrawalRequest.objects.get().status == S.INITIATED


def test_duplicate_signal_is_deduplicated(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "processing")
    signal(client, "processing")
    assert WithdrawalSignal.objects.count() == 1


def test_sent_signal_records_amount_and_txn_id(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "sent", amount="100.0000", currency="USD", txn_id="TT-777")
    request = WithdrawalRequest.objects.get()
    assert request.status == S.TIKTOK_SENT
    assert request.amount_usd == Decimal("100.0000")
    assert request.tiktok_txn_id == "TT-777"


def test_signals_never_create_ledger_entries(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "processing")
    signal(client, "sent", amount="100.0000", txn_id="TT-1")
    assert LedgerEntry.objects.count() == 0


def test_rejected_signal_closes_the_request(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "rejected")
    request = WithdrawalRequest.objects.get()
    assert request.status == S.TIKTOK_REJECTED
    assert request.closed_at is not None


def test_creator_answering_no_cancels_the_request(client, ready):
    code = client.post(reverse("api_v1:withdrawals"), {}, format="json").data["withdrawal"]["code"]
    response = client.post(
        reverse("api_v1:withdrawal-signals"),
        {"source": "manual", "kind": "not_completed", "code": code, "payload": {"answer": "no"}},
        format="json",
    )
    assert response.status_code == 202
    request = WithdrawalRequest.objects.get()
    assert request.status == S.CANCELLED
    assert LedgerEntry.objects.count() == 0


def test_out_of_order_signal_is_ignored(client, ready):
    """إشارة «قيد المعالجة» بعد «أُرسل» لا ترجع بالحالة للخلف."""
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "sent", txn_id="TT-2")
    signal(client, "processing", payload={"late": True})
    assert WithdrawalRequest.objects.get().status == S.TIKTOK_SENT


# --- عرض الحالة ------------------------------------------------------------

def test_withdrawal_detail_shows_timeline(client, ready):
    code = client.post(reverse("api_v1:withdrawals"), {}, format="json").data["withdrawal"]["code"]
    signal(client, "processing")
    response = client.get(reverse("api_v1:withdrawal-detail", args=[code]))
    assert response.status_code == 200
    timeline = {step["status"]: step["done"] for step in response.data["timeline"]}
    assert timeline[S.INITIATED] is True
    assert timeline[S.TIKTOK_PROCESSING] is True
    assert timeline[S.RECEIVED_EG] is False


def test_creator_cannot_see_another_creators_request(
    client, ready, other_creator, receiving_account
):
    foreign = WithdrawalRequest.objects.create(
        creator=other_creator, receiving_account=receiving_account, initiated_at=timezone.now()
    )
    response = client.get(reverse("api_v1:withdrawal-detail", args=[foreign.code]))
    assert response.status_code == 404


def test_profile_lists_recent_withdrawals(client, ready):
    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    response = client.get(reverse("api_v1:creator-me"))
    assert len(response.data["recent_withdrawals"]) == 1
    assert response.data["setup_completed"] is True


# --- المهل الزمنية ---------------------------------------------------------

def test_stale_request_prompts_the_creator(client, ready, settings):
    from datetime import timedelta

    from apps.withdrawals.tasks import ask_creator_about_stale_requests

    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    WithdrawalRequest.objects.update(
        initiated_at=timezone.now()
        - timedelta(minutes=settings.WITHDRAWAL_OPEN_WINDOW_MINUTES + 1)
    )
    assert ask_creator_about_stale_requests() == 1
    request = WithdrawalRequest.objects.get()
    assert request.stale_prompt_sent_at is not None
    assert request.status == S.INITIATED  # السؤال لا يلغي الطلب وحده
    # لا يُسأل المبدع مرتين عن الطلب نفسه
    assert ask_creator_about_stale_requests() == 0


def test_request_with_signal_is_not_prompted(client, ready):
    from datetime import timedelta

    from apps.withdrawals.tasks import ask_creator_about_stale_requests

    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "processing")
    WithdrawalRequest.objects.update(initiated_at=timezone.now() - timedelta(hours=2))
    assert ask_creator_about_stale_requests() == 0


def test_sent_request_becomes_not_received_after_deadline(client, ready, settings):
    from datetime import timedelta

    from apps.withdrawals.tasks import flag_not_received

    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "sent", txn_id="TT-9")
    WithdrawalRequest.objects.update(
        sent_at=timezone.now() - timedelta(days=settings.WITHDRAWAL_NOT_RECEIVED_DAYS + 1)
    )
    assert flag_not_received() == 1
    assert WithdrawalRequest.objects.get().status == S.NOT_RECEIVED
    assert LedgerEntry.objects.count() == 0


def test_not_received_deadline_ignores_recent_requests(client, ready):
    from apps.withdrawals.tasks import flag_not_received

    client.post(reverse("api_v1:withdrawals"), {}, format="json")
    signal(client, "sent", txn_id="TT-10")
    assert flag_not_received() == 0
    assert WithdrawalRequest.objects.get().status == S.TIKTOK_SENT
