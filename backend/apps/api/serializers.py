"""مسلسِلات واجهة تطبيق المبدع.

قاعدة العرض: لا يُعاد للمبدع شيء يخص الجانب المصري إلا بيانات التعبئة نفسها،
ولا يُعاد أي توكن من TikTok إطلاقًا.
"""
from rest_framework import serializers

from apps.withdrawals.models import (
    SignalKind,
    SignalSource,
    WithdrawalRequest,
    WithdrawalStatus,
)

# المصادر التي يُسمح لتطبيق المبدع بإرسالها. البريد والبنك يصلان عبر الخادم لا الجهاز.
CREATOR_ALLOWED_SOURCES = [SignalSource.NOTIFICATION, SignalSource.MANUAL]
CREATOR_ALLOWED_KINDS = [
    SignalKind.PROCESSING,
    SignalKind.SENT,
    SignalKind.REJECTED,
    SignalKind.NOT_COMPLETED,
]


class TikTokExchangeSerializer(serializers.Serializer):
    """كود Login Kit كما يعود من تطبيق TikTok."""

    code = serializers.CharField(max_length=512)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class PhoneVerifySerializer(serializers.Serializer):
    """بلا رمز: أرسل رمزًا. مع رمز: تحقّق منه."""

    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=10, required=False, allow_blank=True)
    device_id = serializers.CharField(max_length=128, required=False, allow_blank=True)


class RefreshSerializer(serializers.Serializer):
    """تجديد رمز الوصول برمز التجديد المربوط بالجهاز."""

    refresh = serializers.CharField(max_length=1024)


class ConsentSerializer(serializers.Serializer):
    """تسجيل الموافقة على الشروط."""

    terms_version = serializers.CharField(max_length=30)
    content_hash = serializers.CharField(max_length=64)
    device_fingerprint = serializers.CharField(max_length=128, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=["ar", "en"], default="ar")


class DeviceSerializer(serializers.Serializer):
    """تسجيل جهاز مع رمز سلامته ورمز إشعاراته."""

    device_id = serializers.CharField(max_length=128)
    integrity_token = serializers.CharField(max_length=4096, required=False, allow_blank=True)
    fcm_token = serializers.CharField(max_length=255, required=False, allow_blank=True)
    model = serializers.CharField(max_length=100, required=False, allow_blank=True)
    os_version = serializers.CharField(max_length=40, required=False, allow_blank=True)
    app_version = serializers.CharField(max_length=20, required=False, allow_blank=True)
    permissions = serializers.DictField(required=False, default=dict)


class SignalSerializer(serializers.Serializer):
    """إشارة ملتقطة من الجهاز عن حالة السحب داخل TikTok."""

    source = serializers.ChoiceField(choices=CREATOR_ALLOWED_SOURCES)
    kind = serializers.ChoiceField(choices=CREATOR_ALLOWED_KINDS)
    code = serializers.CharField(max_length=12, required=False, allow_blank=True)
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True)
    txn_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    package_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    package_sig_ok = serializers.BooleanField(default=False)
    payload = serializers.DictField(required=False, default=dict)


class WithdrawalSerializer(serializers.ModelSerializer):
    """طلب سحب كما يراه المبدع."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WithdrawalRequest
        fields = [
            "code",
            "status",
            "status_label",
            "amount_usd",
            "amount_egp",
            "fee_egp",
            "net_amount_egp",
            "initiated_at",
            "processing_at",
            "sent_at",
            "received_at",
            "paid_at",
        ]
        read_only_fields = fields


class WithdrawalTimelineSerializer(WithdrawalSerializer):
    """تفاصيل الطلب مع خط زمني للحالات."""

    timeline = serializers.SerializerMethodField()

    class Meta(WithdrawalSerializer.Meta):
        fields = [*WithdrawalSerializer.Meta.fields, "timeline"]
        read_only_fields = fields

    def get_timeline(self, obj) -> list[dict]:
        steps = [
            (WithdrawalStatus.INITIATED, obj.initiated_at),
            (WithdrawalStatus.TIKTOK_PROCESSING, obj.processing_at),
            (WithdrawalStatus.TIKTOK_SENT, obj.sent_at),
            (WithdrawalStatus.RECEIVED_EG, obj.received_at),
            (WithdrawalStatus.PAID, obj.paid_at),
        ]
        return [
            {
                "status": status,
                "label": WithdrawalStatus(status).label,
                "at": moment,
                "done": moment is not None,
            }
            for status, moment in steps
        ]


class AutofillDatasetSerializer(serializers.Serializer):
    """بيانات التعبئة داخل TikTok — الحقل الوحيد الذي يرى فيه الجهاز حساب الاستلام."""

    account_type = serializers.CharField()
    identifier = serializers.CharField()
    beneficiary_name = serializers.CharField()
    bank_name = serializers.CharField()


class CreatorProfileSerializer(serializers.Serializer):
    """ملف المبدع وحالته ورصيده."""

    id = serializers.UUIDField()
    display_name = serializers.CharField()
    phone = serializers.CharField()
    phone_verified = serializers.BooleanField()
    status = serializers.CharField()
    preferred_language = serializers.CharField()
    setup_completed = serializers.BooleanField()
    balance_egp = serializers.DecimalField(max_digits=18, decimal_places=4)
    tiktok = serializers.DictField(allow_null=True)
    recent_withdrawals = WithdrawalSerializer(many=True)
