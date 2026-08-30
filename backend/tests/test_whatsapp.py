"""قناة WhatsApp: رسالة لكل حالة، الويب هوك الموقَّع، ورد «وصل» يحدّث الطلب."""
import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from django.test import Client

from apps.ledger import services as ledger
from apps.ledger.models import LedgerEntry
from apps.messaging.models import Channel, Message, MessageReply, MessageStatus, MessageTemplate
from apps.messaging.services import sync_templates
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import SignalSource, WithdrawalSignal
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db

WEBHOOK = "/api/v1/webhooks/whatsapp"
SECRET = "test-app-secret"


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def post_webhook(payload: dict, *, signature: str | None = None):
    body = json.dumps(payload).encode()
    return Client().post(
        WEBHOOK,
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=signature if signature is not None else sign(body),
    )


def button_reply(from_number: str, button_id: str, *, context_id: str = "", message_id="wamid.in1"):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": from_number.lstrip("+"),
                                    "type": "interactive",
                                    "context": {"id": context_id} if context_id else {},
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": button_id, "title": button_id},
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def owner_messages(request=None):
    qs = Message.objects.filter(channel=Channel.WHATSAPP)
    return qs.filter(request=request) if request else qs


# --- القوالب ----------------------------------------------------------------

def test_sync_creates_templates_in_both_languages():
    created = sync_templates()
    assert created > 0
    assert MessageTemplate.objects.filter(language="ar").count() == created / 2
    assert MessageTemplate.objects.filter(language="en").count() == created / 2
    # لا يُنشئ مكررات عند إعادة التشغيل
    assert sync_templates() == 0


def test_admin_can_edit_template_body(request_initiated, owner):
    sync_templates()
    template = MessageTemplate.objects.get(key="owner_processing", language="ar")
    template.body = "نص معدَّل للطلب {code}"
    template.save()

    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    message = owner_messages(request_initiated).first()
    assert message.body == f"نص معدَّل للطلب {request_initiated.code}"


def test_broken_template_falls_back_to_default(request_initiated):
    sync_templates()
    template = MessageTemplate.objects.get(key="owner_processing", language="ar")
    template.body = "متغيّر غير موجود {nope}"
    template.save()

    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    message = owner_messages(request_initiated).first()
    assert request_initiated.code in message.body


# --- رسالة لكل حالة ---------------------------------------------------------

@pytest.mark.parametrize(
    "path,expected",
    [
        ([S.TIKTOK_PROCESSING], 1),
        ([S.TIKTOK_PROCESSING, S.TIKTOK_SENT], 2),
        ([S.TIKTOK_SENT, S.NOT_RECEIVED], 2),
    ],
)
def test_owner_is_messaged_on_every_relevant_state(request_initiated, path, expected):
    for target in path:
        sm.transition(request_initiated, target)
    owner_phone = request_initiated.receiving_account.owner.whatsapp_phone
    assert owner_messages(request_initiated).filter(to_ref=owner_phone).count() == expected


def test_message_carries_code_and_amount(request_initiated):
    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    body = owner_messages(request_initiated).first().body
    assert request_initiated.code in body
    assert "100" in body


def test_admin_is_alerted_on_rejection(request_initiated, settings):
    sm.transition(request_initiated, S.TIKTOK_REJECTED)
    admin_number = settings.ADMIN_WHATSAPP_NUMBERS[0]
    assert owner_messages(request_initiated).filter(to_ref=admin_number).exists()


def test_admin_is_alerted_when_not_received(request_initiated, settings):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    sm.transition(request_initiated, S.NOT_RECEIVED)
    admin_number = settings.ADMIN_WHATSAPP_NUMBERS[0]
    assert owner_messages(request_initiated).filter(to_ref=admin_number).exists()


def test_no_message_for_states_that_do_not_concern_the_owner(request_initiated):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    before = owner_messages(request_initiated).count()
    sm.transition(request_initiated, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    sm.transition(request_initiated, S.APPROVED)
    # received_eg يُبلَّغ به، أما approved فلا يعني صاحب الحساب
    assert owner_messages(request_initiated).count() == before + 1


def test_messaging_failure_does_not_break_a_financial_transition(request_initiated, monkeypatch):
    """لو انهارت قناة الرسائل، القيد المالي يبقى سليمًا."""
    def explode(*args, **kwargs):
        raise RuntimeError("قناة معطلة")

    monkeypatch.setattr("apps.messaging.services.on_transition", explode)
    sm.transition(request_initiated, S.TIKTOK_SENT)
    result = sm.transition(request_initiated, S.RECEIVED_EG, amount_egp=Decimal("4850"))
    assert result.status == S.RECEIVED_EG
    assert ledger.creator_balance(request_initiated.creator_id) == Decimal("4850.0000")


# --- أمن الويب هوك ----------------------------------------------------------

def test_webhook_verification_handshake(settings):
    response = Client().get(
        WEBHOOK,
        {
            "hub.mode": "subscribe",
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.content.decode() == "12345"


def test_webhook_verification_rejects_wrong_token():
    response = Client().get(
        WEBHOOK,
        {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
    )
    assert response.status_code == 403


def test_unsigned_payload_is_rejected(request_initiated, owner):
    response = post_webhook(button_reply(owner.whatsapp_phone, "received"), signature="")
    assert response.status_code == 403
    assert MessageReply.objects.count() == 0


def test_forged_signature_is_rejected(request_initiated, owner):
    response = post_webhook(
        button_reply(owner.whatsapp_phone, "received"), signature="sha256=" + "0" * 64
    )
    assert response.status_code == 403
    assert MessageReply.objects.count() == 0


# --- رد صاحب الحساب ---------------------------------------------------------

def test_owner_reply_received_credits_the_creator(request_initiated, owner, fx_rate):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    original = owner_messages(request_initiated).filter(to_ref=owner.whatsapp_phone).first()
    original.provider_message_id = "wamid.out1"
    original.status = MessageStatus.SENT
    original.save()

    response = post_webhook(
        button_reply(owner.whatsapp_phone, "received", context_id="wamid.out1")
    )
    assert response.status_code == 200

    request_initiated.refresh_from_db()
    assert request_initiated.status == S.RECEIVED_EG
    assert request_initiated.amount_egp == Decimal("4850.0000")
    assert ledger.creator_balance(request_initiated.creator_id) == Decimal("4850.0000")
    assert WithdrawalSignal.objects.filter(source=SignalSource.OWNER_WA).count() == 1


def test_owner_reply_not_received_does_not_change_status(request_initiated, owner, fx_rate):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    post_webhook(button_reply(owner.whatsapp_phone, "not_received"))
    request_initiated.refresh_from_db()
    assert request_initiated.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_large_amount_needs_bank_proof_not_a_reply(request_initiated, owner, fx_rate, settings):
    """فوق حد الثقة لا يكفي رد بشري لتقييد المال."""
    settings.OWNER_CONFIRMATION_MAX_AMOUNT_USD = Decimal("50")
    sm.transition(request_initiated, S.TIKTOK_SENT)
    post_webhook(button_reply(owner.whatsapp_phone, "received"))

    request_initiated.refresh_from_db()
    assert request_initiated.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0

    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="owner.confirmation_needs_bank_proof").exists()


def test_reply_without_a_known_amount_is_not_credited(
    creator, receiving_account, assignment, owner, fx_rate
):
    from django.utils import timezone

    from apps.withdrawals.models import WithdrawalRequest

    request = WithdrawalRequest.objects.create(
        creator=creator, receiving_account=receiving_account, initiated_at=timezone.now()
    )
    sm.transition(request, S.TIKTOK_SENT)
    post_webhook(button_reply(owner.whatsapp_phone, "received"))
    request.refresh_from_db()
    assert request.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_duplicate_webhook_delivery_is_ignored(request_initiated, owner, fx_rate):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    payload = button_reply(owner.whatsapp_phone, "received")
    post_webhook(payload)
    post_webhook(payload)
    assert MessageReply.objects.count() == 1
    assert LedgerEntry.objects.filter(request_id=request_initiated.id).count() == 2


def test_reply_from_an_unknown_number_changes_nothing(request_initiated, fx_rate):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    post_webhook(button_reply("+201555555555", "received"))
    request_initiated.refresh_from_db()
    assert request_initiated.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_free_text_reply_is_stored_but_does_not_move_money(request_initiated, owner, fx_rate):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.text1",
                                    "from": owner.whatsapp_phone.lstrip("+"),
                                    "type": "text",
                                    "text": {"body": "شكرًا"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    post_webhook(payload)
    request_initiated.refresh_from_db()
    assert MessageReply.objects.count() == 1
    assert request_initiated.status == S.TIKTOK_SENT
    assert LedgerEntry.objects.count() == 0


def test_arabic_text_reply_is_understood(request_initiated, owner, fx_rate):
    """صاحب الحساب قد يكتب «وصل» بدل الضغط على الزر."""
    sm.transition(request_initiated, S.TIKTOK_SENT)
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.text2",
                                    "from": owner.whatsapp_phone.lstrip("+"),
                                    "type": "text",
                                    "text": {"body": "وصل"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    post_webhook(payload)
    request_initiated.refresh_from_db()
    assert request_initiated.status == S.RECEIVED_EG


# --- حالات التسليم ----------------------------------------------------------

def test_delivery_status_updates_the_message(request_initiated):
    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    message = owner_messages(request_initiated).first()
    message.provider_message_id = "wamid.out9"
    message.save()

    post_webhook(
        {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": "wamid.out9", "status": "delivered"}]}}
                    ]
                }
            ]
        }
    )
    message.refresh_from_db()
    assert message.status == MessageStatus.DELIVERED
    assert message.delivered_at is not None


# --- الإرسال الفعلي ---------------------------------------------------------

def test_send_task_marks_message_sent(request_initiated, monkeypatch):
    from apps.messaging.tasks import send_whatsapp_message
    from apps.messaging.whatsapp import FakeWhatsAppChannel

    channel = FakeWhatsAppChannel()
    monkeypatch.setattr("apps.messaging.tasks.get_channel", lambda: channel)

    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    message = owner_messages(request_initiated).first()
    result = send_whatsapp_message(
        str(message.id), {"template_name": "wd_owner_processing", "language": "ar"}
    )

    message.refresh_from_db()
    assert message.status == MessageStatus.SENT
    assert message.provider_message_id == result
    assert channel.sent[0].to == request_initiated.receiving_account.owner.whatsapp_phone


def test_failed_send_is_marked_and_can_be_requeued(request_initiated, monkeypatch):
    from apps.messaging.tasks import retry_failed_messages

    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    message = owner_messages(request_initiated).first()
    message.status = MessageStatus.FAILED
    message.failure_reason = "انقطاع"
    message.save()

    assert retry_failed_messages() == 1
    message.refresh_from_db()
    assert message.status == MessageStatus.QUEUED
    assert message.failure_reason == ""
