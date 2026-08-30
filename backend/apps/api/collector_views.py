"""مسار تطبيق الجامع: استقبال الوارد البنكي موقّعًا بـ HMAC.

الجهاز ليس مستخدمًا ولا يملك جلسة. يوقّع كل طلب بسرّه الخاص، ويُرفض أي طلب
بلا توقيع صحيح داخل نافذة زمنية ضيقة.
"""
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.receiving.models import ReceivingAccount
from apps.reconciliation import services as reconciliation
from apps.reconciliation.models import MatchStatus, TransferSource

from .views import error


class IncomingTransferSerializer(serializers.Serializer):
    """تحويل وارد كما يقرؤه الجامع من رسالة البنك."""

    account_identifier = serializers.CharField(max_length=120)
    amount_egp = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    received_at = serializers.DateTimeField()
    bank_ref = serializers.CharField(max_length=120, required=False, allow_blank=True)
    sender_hint = serializers.CharField(max_length=200, required=False, allow_blank=True)
    source = serializers.ChoiceField(
        choices=[TransferSource.SMS, TransferSource.NOTIFICATION], default=TransferSource.SMS
    )
    dedupe_key = serializers.CharField(max_length=120)
    raw_payload = serializers.DictField(required=False, default=dict)


class IncomingTransferView(APIView):
    """POST /api/v1/reconciliation/incoming."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            device = reconciliation.authenticate_collector(
                collector_id=request.headers.get("X-Collector-Id", ""),
                timestamp=request.headers.get("X-Timestamp", ""),
                signature=request.headers.get("X-Signature", ""),
                body=request.body,
            )
        except reconciliation.CollectorAuthError as exc:
            return error(str(exc), code="collector_auth", http_status=status.HTTP_403_FORBIDDEN)

        serializer = IncomingTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        account = ReceivingAccount.objects.filter(identifier=data["account_identifier"]).first()
        if account is None:
            # حساب غير معروف: لا نُنشئ شيئًا، ونُبلّغ الجهاز ليتوقف عن إعادة الإرسال
            return error(
                "حساب الاستلام غير معروف", code="unknown_account", http_status=status.HTTP_200_OK
            )

        transfer, created = reconciliation.record_incoming(
            receiving_account=account,
            amount_egp=data["amount_egp"],
            received_at=data["received_at"],
            bank_ref=data.get("bank_ref", ""),
            sender_hint=data.get("sender_hint", ""),
            source=data["source"],
            raw_payload=data.get("raw_payload") or {},
            dedupe_key=data["dedupe_key"],
            collector=device,
        )

        return Response(
            {
                "accepted": True,
                "duplicate": not created,
                "transfer_id": str(transfer.id),
                "match_status": transfer.match_status,
                "matched_request": (
                    transfer.matched_request.code if transfer.matched_request_id else None
                ),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TransferMatchStatus:
    """أسماء الحالات لتسهيل قراءتها من الاختبارات."""

    MATCHED = MatchStatus.MATCHED
    AMBIGUOUS = MatchStatus.AMBIGUOUS
    UNMATCHED = MatchStatus.UNMATCHED
