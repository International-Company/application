"""إشعارات المبدع عبر FCM — خلف واجهة، وكل رسالة تُسجَّل في جدول messages."""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from .models import Channel, Message, MessageStatus

logger = logging.getLogger("mobde3.push")


class PushSender(ABC):
    """العقد: إرسال إشعار إلى رمز جهاز."""

    @abstractmethod
    def send(self, token: str, title: str, body: str, data: dict | None = None) -> str: ...


@dataclass
class ConsolePushSender(PushSender):
    """بديل التطوير والاختبار."""

    sent: list = field(default_factory=list)

    def send(self, token: str, title: str, body: str, data: dict | None = None) -> str:
        self.sent.append({"token": token, "title": title, "body": body, "data": data or {}})
        logger.info("إشعار: %s — %s", title, body)
        return f"console-push-{len(self.sent)}"


def get_push_sender() -> PushSender:
    from django.utils.module_loading import import_string

    return import_string(settings.PUSH_SENDER)()


def notify_creator(creator, *, title: str, body: str, request=None, data: dict | None = None):
    """إرسال إشعار إلى كل أجهزة المبدع النشطة، مع تسجيل كل محاولة."""
    devices = creator.devices.filter(is_active=True).exclude(fcm_token="")
    sender = get_push_sender()
    records = []
    for device in devices:
        message = Message.objects.create(
            channel=Channel.FCM,
            to_ref=device.fcm_token,
            request=request,
            body=f"{title}\n{body}",
        )
        try:
            provider_id = sender.send(device.fcm_token, title, body, data)
        except Exception as exc:  # noqa: BLE001 — فشل الإشعار لا يُسقط عملية مالية
            message.status = MessageStatus.FAILED
            message.failure_reason = str(exc)[:300]
            message.save(update_fields=["status", "failure_reason", "updated_at"])
            continue
        message.provider_message_id = provider_id
        message.status = MessageStatus.SENT
        message.sent_at = timezone.now()
        message.save(
            update_fields=["provider_message_id", "status", "sent_at", "updated_at"]
        )
        records.append(message)
    return records
