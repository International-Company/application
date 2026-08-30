"""إرسال رسائل الحالات ومعالجة الردود الواردة.

قاعدة حاكمة: رد صاحب الحساب «وصل» إشارة بشرية لا دليل بنكي. لذلك يُقبل وحده
تحت حد مبلغ معيّن فقط، وفوقه يُسجَّل وينتظر دليلًا أقوى أو قرار الإدارة.
"""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.common.money import quantize
from apps.withdrawals.models import (
    SignalKind,
    SignalSource,
    WithdrawalRequest,
    WithdrawalSignal,
    WithdrawalStatus,
)

from . import catalog
from .models import Channel, Message, MessageReply, MessageStatus, MessageTemplate


def _language_for(preferred: str) -> str:
    return "en" if preferred == "en" else "ar"


def _render(definition: dict, language: str, context: dict) -> tuple[str, MessageTemplate | None]:
    """نص الرسالة من قالب قاعدة البيانات إن وُجد، وإلا من الفهرس الافتراضي."""
    template = MessageTemplate.objects.filter(
        key=definition["key"], channel=Channel.WHATSAPP, language=language, is_active=True
    ).first()
    body = template.body if template else definition[language]
    try:
        return body.format(**context), template
    except KeyError:
        # قالب عدّلته الإدارة بمتغيّر غير معروف: يُستعمل النص الافتراضي
        return definition[language].format(**context), template


def _context_for(request: WithdrawalRequest) -> dict:
    return {
        "code": request.code,
        "creator": request.creator.display_name or request.creator.phone,
        "amount_usd": str(request.amount_usd) if request.amount_usd else "—",
        "amount_egp": str(request.amount_egp) if request.amount_egp else "—",
    }


def _queue(
    *,
    to: str,
    body: str,
    request: WithdrawalRequest,
    template: MessageTemplate | None,
    definition: dict,
    language: str,
) -> Message:
    """إنشاء رسالة في الطابور وجدولة إرسالها بعد نجاح المعاملة."""
    message = Message.objects.create(
        channel=Channel.WHATSAPP,
        to_ref=to,
        request=request,
        template=template,
        body=body,
        status=MessageStatus.QUEUED,
    )
    payload = {
        "template_name": definition["provider_template_name"],
        "language": language,
        "parameters": [body],
    }
    transaction.on_commit(lambda: _dispatch(message.id, payload))
    return message


def _dispatch(message_id, payload: dict) -> None:
    from .tasks import send_whatsapp_message

    send_whatsapp_message.delay(str(message_id), payload)


def notify_owner(request: WithdrawalRequest, status: str) -> Message | None:
    """رسالة صاحب الحساب المصري عند الحالات التي تعنيه."""
    definition = catalog.OWNER_TEMPLATES.get(status)
    if definition is None or request.receiving_account_id is None:
        return None

    owner = request.receiving_account.owner
    if not owner.whatsapp_phone:
        return None

    language = _language_for(owner.preferred_language)
    body, template = _render(definition, language, _context_for(request))
    return _queue(
        to=owner.whatsapp_phone,
        body=body,
        request=request,
        template=template,
        definition=definition,
        language=language,
    )


def notify_admins(request: WithdrawalRequest, status: str) -> list[Message]:
    """تنبيه الإدارة على واتساب في الحالات التي تحتاج تدخلًا."""
    definition = catalog.ADMIN_TEMPLATES.get(status)
    if definition is None:
        return []

    numbers = [number for number in settings.ADMIN_WHATSAPP_NUMBERS if number]
    if not numbers:
        return []

    language = "ar"
    body, template = _render(definition, language, _context_for(request))
    return [
        _queue(
            to=number,
            body=body,
            request=request,
            template=template,
            definition=definition,
            language=language,
        )
        for number in numbers
    ]


def on_transition(request: WithdrawalRequest, status: str) -> None:
    """نقطة واحدة تُستدعى من آلة الحالات بعد كل انتقال."""
    notify_owner(request, status)
    notify_admins(request, status)


# --- الردود الواردة ---------------------------------------------------------


def _resolve_request_from_reply(context_message_id: str, from_number: str):
    """الطلب المقصود بالرد: عبر معرّف الرسالة الأصلية، وإلا آخر طلب مفتوح للرقم."""
    if context_message_id:
        original = Message.objects.filter(provider_message_id=context_message_id).first()
        if original is not None and original.request_id is not None:
            return original.request, original

    open_message = (
        Message.objects.filter(
            to_ref=from_number,
            channel=Channel.WHATSAPP,
            request__status__in=[WithdrawalStatus.TIKTOK_SENT, WithdrawalStatus.NOT_RECEIVED],
        )
        .order_by("-created_at")
        .first()
    )
    if open_message is not None:
        return open_message.request, open_message
    return None, None


@transaction.atomic
def handle_inbound_reply(
    *,
    from_number: str,
    provider_message_id: str,
    context_message_id: str = "",
    button_id: str = "",
    text: str = "",
    payload: dict | None = None,
) -> MessageReply:
    """تسجيل رد وارد ومحاولة تحريك الطلب به."""
    existing = MessageReply.objects.filter(provider_message_id=provider_message_id).first()
    if existing is not None:
        return existing

    request, original = _resolve_request_from_reply(context_message_id, from_number)
    reply = MessageReply.objects.create(
        message=original,
        from_ref=from_number,
        reply_payload=payload or {},
        button_id=button_id,
        text=text,
        received_at=timezone.now(),
        provider_message_id=provider_message_id,
    )

    meaning = catalog.BUTTON_MEANING.get(button_id) or catalog.BUTTON_MEANING.get(text.strip())
    if request is None or meaning is None:
        return reply

    _apply_owner_confirmation(request, reply, meaning)
    return reply


def _expected_amount_egp(request: WithdrawalRequest) -> Decimal | None:
    """المبلغ المتوقع بالجنيه من المبلغ الدولاري وسعر الصرف المعتمد."""
    from apps.pricing import services as pricing

    if request.amount_egp:
        return quantize(request.amount_egp)
    if not request.amount_usd:
        return None
    rate = pricing.latest_fx_rate()
    if rate is None:
        return None
    return quantize(Decimal(request.amount_usd) * rate.rate)


def _apply_owner_confirmation(
    request: WithdrawalRequest, reply: MessageReply, meaning: str
) -> None:
    """ترجمة رد صاحب الحساب إلى إشارة، ثم إلى انتقال حالة إن جاز."""
    from apps.pricing import services as pricing
    from apps.withdrawals import state_machine as sm

    WithdrawalSignal.objects.create(
        request=request,
        creator=request.creator,
        source=SignalSource.OWNER_WA,
        kind=SignalKind.RECEIVED if meaning == "received" else SignalKind.NOT_COMPLETED,
        raw_payload=reply.reply_payload,
        parsed_at=timezone.now(),
        dedupe_key=f"owner_wa:{reply.provider_message_id}",
    )
    reply.processed_at = timezone.now()
    reply.save(update_fields=["processed_at", "updated_at"])

    if meaning != "received":
        # «لم يصل» لا تُغيّر الحالة بنفسها؛ المهلة الزمنية هي التي تحسم
        audit.record(
            action="owner.reported_not_received",
            entity="withdrawal_request",
            entity_id=request.id,
            actor_type=ActorType.OWNER,
            actor_label=reply.from_ref,
            after={"code": request.code},
        )
        return

    if not sm.can_transition(request.status, WithdrawalStatus.RECEIVED_EG):
        return

    # حد الثقة: فوقه لا يكفي رد بشري، ويلزم دليل بنكي أو قرار إدارة
    amount_usd = Decimal(request.amount_usd or 0)
    if amount_usd > settings.OWNER_CONFIRMATION_MAX_AMOUNT_USD:
        audit.record(
            action="owner.confirmation_needs_bank_proof",
            entity="withdrawal_request",
            entity_id=request.id,
            actor_type=ActorType.OWNER,
            actor_label=reply.from_ref,
            after={"code": request.code, "amount_usd": str(amount_usd)},
        )
        return

    amount_egp = _expected_amount_egp(request)
    if amount_egp is None or amount_egp <= 0:
        audit.record(
            action="owner.confirmation_without_amount",
            entity="withdrawal_request",
            entity_id=request.id,
            actor_type=ActorType.OWNER,
            actor_label=reply.from_ref,
            after={"code": request.code},
        )
        return

    rate = pricing.latest_fx_rate()
    sm.transition(
        request,
        WithdrawalStatus.RECEIVED_EG,
        actor=sm.Actor(type=ActorType.OWNER, label=reply.from_ref),
        amount_egp=amount_egp,
        evidence={
            "source": SignalSource.OWNER_WA,
            "amount_basis": "fx_rate",
            "fx_rate": str(rate.rate) if rate else None,
        },
    )


def sync_templates() -> int:
    """إنشاء القوالب الافتراضية في قاعدة البيانات لتعدّلها الإدارة."""
    created = 0
    for _audience, definition in catalog.all_definitions():
        for language in ("ar", "en"):
            _, was_created = MessageTemplate.objects.get_or_create(
                key=definition["key"],
                channel=Channel.WHATSAPP,
                language=language,
                defaults={
                    "provider_template_name": definition["provider_template_name"],
                    "body": definition[language],
                    "buttons_json": definition["buttons"],
                },
            )
            created += int(was_created)
    return created
