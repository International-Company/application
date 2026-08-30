"""إرسال رسائل واتساب في الخلفية مع إعادة المحاولة."""
from celery import shared_task
from django.utils import timezone

from .models import Message, MessageStatus
from .whatsapp import OutboundTemplate, WhatsAppError, get_channel


@shared_task(
    name="messaging.send_whatsapp_message",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_whatsapp_message(self, message_id: str, payload: dict):
    """إرسال رسالة واحدة وتحديث حالتها. فشل الإرسال لا يمس أي قيد مالي."""
    message = Message.objects.filter(pk=message_id).first()
    if message is None or message.status != MessageStatus.QUEUED:
        return None

    outbound = OutboundTemplate(
        to=message.to_ref,
        template_name=payload.get("template_name", ""),
        language=payload.get("language", "ar"),
        parameters=payload.get("parameters", []),
    )

    try:
        provider_id = get_channel().send_template(outbound)
    except WhatsAppError as exc:
        message.status = MessageStatus.FAILED
        message.failure_reason = str(exc)[:300]
        message.save(update_fields=["status", "failure_reason", "updated_at"])
        raise self.retry(exc=exc) from exc

    message.provider_message_id = provider_id
    message.status = MessageStatus.SENT
    message.sent_at = timezone.now()
    message.failure_reason = ""
    message.save(
        update_fields=[
            "provider_message_id",
            "status",
            "sent_at",
            "failure_reason",
            "updated_at",
        ]
    )
    return provider_id


@shared_task(name="messaging.retry_failed_messages")
def retry_failed_messages() -> int:
    """إعادة الفاشلة إلى الطابور ليعيد الإرسال محاولتها."""
    failed = Message.objects.filter(status=MessageStatus.FAILED)
    count = failed.count()
    failed.update(status=MessageStatus.QUEUED, failure_reason="")
    return count
