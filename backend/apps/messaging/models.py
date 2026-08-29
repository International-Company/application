"""قوالب واتساب وسجل الرسائل والردود."""
from django.db import models

from apps.common.models import TimestampedModel
from apps.withdrawals.models import WithdrawalRequest


class Channel(models.TextChoices):
    WHATSAPP = "whatsapp", "واتساب"
    FCM = "fcm", "إشعار تطبيق"


class MessageTemplate(TimestampedModel):
    """قالب رسالة معتمد لدى Meta، بنسختين عربية وإنجليزية."""

    key = models.CharField(max_length=60, help_text="مفتاح داخلي مثل withdrawal_sent_owner")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.WHATSAPP)
    language = models.CharField(max_length=2, choices=[("ar", "العربية"), ("en", "English")])
    provider_template_name = models.CharField(max_length=100, blank=True)
    body = models.TextField(help_text="النص مع متغيرات {code} {amount} {creator}")
    buttons_json = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "message_templates"
        constraints = [
            models.UniqueConstraint(
                fields=["key", "channel", "language"], name="uniq_template_key_lang"
            )
        ]

    def render(self, context: dict) -> str:
        """تعبئة متغيرات القالب."""
        return self.body.format(**context)


class MessageStatus(models.TextChoices):
    QUEUED = "queued", "في الطابور"
    SENT = "sent", "أُرسلت"
    DELIVERED = "delivered", "وصلت"
    READ = "read", "قُرئت"
    FAILED = "failed", "فشلت"


class Message(TimestampedModel):
    """رسالة صادرة واحدة وسجل حالتها."""

    channel = models.CharField(max_length=10, choices=Channel.choices)
    to_ref = models.CharField(max_length=120, help_text="رقم واتساب أو رمز جهاز FCM")
    template = models.ForeignKey(
        MessageTemplate, on_delete=models.PROTECT, null=True, blank=True, related_name="messages"
    )
    request = models.ForeignKey(
        WithdrawalRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="messages"
    )
    body = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True, db_index=True)
    status = models.CharField(
        max_length=10, choices=MessageStatus.choices, default=MessageStatus.QUEUED, db_index=True
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "messages"
        indexes = [models.Index(fields=["request", "created_at"])]


class MessageReply(TimestampedModel):
    """رد وارد على رسالة — يُربط بالطلب عبر معرّف الرسالة الأصلية."""

    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="replies", null=True, blank=True
    )
    from_ref = models.CharField(max_length=120)
    reply_payload = models.JSONField(default=dict, blank=True)
    button_id = models.CharField(max_length=60, blank=True, help_text="مثل received / not_received")
    text = models.TextField(blank=True)
    received_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "message_replies"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_message_id"],
                condition=~models.Q(provider_message_id=""),
                name="uniq_reply_provider_id",
            )
        ]
