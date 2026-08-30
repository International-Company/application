"""قناة WhatsApp عبر Cloud API من Meta — خلف واجهة.

الرسائل الصادرة قوالب معتمدة مسبقًا لدى Meta. الردود التفاعلية تصل عبر ويب هوك
موقَّع، ويُربط الرد بالطلب عبر معرّف الرسالة الأصلية.
"""
import hashlib
import hmac
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings

from apps.common.errors import DomainError

GRAPH_VERSION = "v21.0"


class WhatsAppError(DomainError):
    """فشل في التخاطب مع WhatsApp Cloud API."""


@dataclass(frozen=True)
class OutboundTemplate:
    """رسالة قالبية صادرة."""

    to: str
    template_name: str
    language: str
    parameters: list[str] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)


class WhatsAppChannel(ABC):
    """العقد الذي تعتمد عليه بقية المنصة."""

    @abstractmethod
    def send_template(self, message: OutboundTemplate) -> str:
        """يعيد معرّف الرسالة لدى المزوّد."""


class CloudApiWhatsAppChannel(WhatsAppChannel):
    """التنفيذ الحقيقي عبر Graph API."""

    def __init__(self, phone_number_id: str = "", access_token: str = ""):
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN

    def send_template(self, message: OutboundTemplate) -> str:
        import requests

        if not self.phone_number_id or not self.access_token:
            raise WhatsAppError("مفاتيح WhatsApp غير مضبوطة في البيئة")

        components = []
        if message.parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in message.parameters],
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": "template",
            "template": {
                "name": message.template_name,
                "language": {"code": message.language},
                "components": components,
            },
        }

        response = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_number_id}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=settings.WHATSAPP_HTTP_TIMEOUT,
        )
        body = response.json()
        if response.status_code >= 400:
            raise WhatsAppError(f"تعذّر إرسال رسالة واتساب: {body}")
        try:
            return body["messages"][0]["id"]
        except (KeyError, IndexError) as exc:
            raise WhatsAppError(f"استجابة غير متوقعة من واتساب: {body}") from exc


@dataclass
class FakeWhatsAppChannel(WhatsAppChannel):
    """بديل التطوير والاختبار — يحتفظ بالرسائل في الذاكرة."""

    sent: list = field(default_factory=list)

    def send_template(self, message: OutboundTemplate) -> str:
        self.sent.append(message)
        return f"wamid.fake.{len(self.sent)}"


def get_channel() -> WhatsAppChannel:
    from django.utils.module_loading import import_string

    return import_string(settings.WHATSAPP_CHANNEL)()


def verify_signature(raw_body: bytes, header: str) -> bool:
    """التحقق من توقيع Meta للويب هوك. بلا سر مضبوط لا يُقبل شيء."""
    secret = settings.WHATSAPP_APP_SECRET
    if not secret or not header:
        return False
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))
