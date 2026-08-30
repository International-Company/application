"""الويب هوكات الواردة من الأطراف الخارجية.

كل ويب هوك يتحقق من توقيعه قبل أن يقرأ محتواه. الحمولة غير الموقّعة تُرفض
ولا تُخزَّن ولا تُحرّك شيئًا.
"""
from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging import services as messaging
from apps.messaging.whatsapp import verify_signature


class WhatsAppWebhookView(APIView):
    """GET للتحقق من الاشتراك، وPOST لاستقبال الردود وحالات التسليم."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        """مصافحة Meta عند ربط الويب هوك."""
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge", "")
        if mode == "subscribe" and token and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("forbidden", status=status.HTTP_403_FORBIDDEN)

    def post(self, request):
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(request.body, signature):
            return Response(
                {"error": {"code": "bad_signature", "message": "توقيع غير صالح"}},
                status=status.HTTP_403_FORBIDDEN,
            )

        handled = 0
        for entry in request.data.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                handled += _handle_change(change.get("value") or {})

        # Meta تعيد الإرسال عند أي رمز غير 200، فالاستجابة دائمًا 200
        return Response({"handled": handled}, status=status.HTTP_200_OK)


def _handle_change(value: dict) -> int:
    """معالجة تغيير واحد: رسائل واردة أو تحديثات حالة."""
    handled = 0

    for message in value.get("messages", []) or []:
        button_id, text = _extract_reply(message)
        messaging.handle_inbound_reply(
            from_number=_normalize(message.get("from", "")),
            provider_message_id=message.get("id", ""),
            context_message_id=(message.get("context") or {}).get("id", ""),
            button_id=button_id,
            text=text,
            payload=message,
        )
        handled += 1

    for update in value.get("statuses", []) or []:
        _apply_delivery_status(update)
        handled += 1

    return handled


def _extract_reply(message: dict) -> tuple[str, str]:
    """استخراج زر الرد أو نصه من صيغ واتساب المختلفة."""
    kind = message.get("type")
    if kind == "button":
        payload = message.get("button") or {}
        return payload.get("payload", "") or payload.get("text", ""), payload.get("text", "")
    if kind == "interactive":
        interactive = message.get("interactive") or {}
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return reply.get("id", ""), reply.get("title", "")
    if kind == "text":
        return "", (message.get("text") or {}).get("body", "")
    return "", ""


def _normalize(number: str) -> str:
    """واتساب يرسل الرقم بلا علامة زائد؛ نوحّده مع ما نخزّنه."""
    number = (number or "").strip()
    return number if number.startswith("+") else f"+{number}" if number else ""


def _apply_delivery_status(update: dict) -> None:
    """تحديث حالة تسليم رسالة صادرة."""
    from django.utils import timezone

    from apps.messaging.models import Message, MessageStatus

    mapping = {
        "sent": MessageStatus.SENT,
        "delivered": MessageStatus.DELIVERED,
        "read": MessageStatus.READ,
        "failed": MessageStatus.FAILED,
    }
    new_status = mapping.get(update.get("status", ""))
    message = Message.objects.filter(provider_message_id=update.get("id", "")).first()
    if message is None or new_status is None:
        return

    message.status = new_status
    if new_status == MessageStatus.DELIVERED and message.delivered_at is None:
        message.delivered_at = timezone.now()
    if new_status == MessageStatus.FAILED:
        errors = update.get("errors") or [{}]
        message.failure_reason = str(errors[0].get("title", ""))[:300]
    message.save(update_fields=["status", "delivered_at", "failure_reason", "updated_at"])
