"""إرسال رسائل SMS — خلف واجهة لأن المزوّد لم يُحسم بعد."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings


class SmsSender(ABC):
    """العقد: إرسال نص إلى رقم."""

    @abstractmethod
    def send(self, phone: str, body: str) -> str:
        """يعيد معرّف الرسالة لدى المزوّد."""


@dataclass
class ConsoleSmsSender(SmsSender):
    """بديل التطوير والاختبار — يحتفظ بالرسائل في الذاكرة."""

    sent: list = field(default_factory=list)

    def send(self, phone: str, body: str) -> str:
        self.sent.append((phone, body))
        return f"console-{len(self.sent)}"


def get_sms_sender() -> SmsSender:
    from django.utils.module_loading import import_string

    return import_string(settings.SMS_SENDER)()
