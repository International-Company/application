"""مسارات تطبيق المبدع — الإصدار v1.

كل مسار هنا للمبدع وحده. جلسات الإدارة تُرفض بصلاحية IsCreator،
ورموز المبدعين تُرفض على مسارات الإدارة بصلاحية IsAdminSession.
"""
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common import tokens
from apps.common.errors import DomainError
from apps.common.permissions import IsCreator, IsVerifiedCreator
from apps.creators import services as creator_services
from apps.creators.models import CreatorDevice, CreatorStatus
from apps.integrations import services as integration_services
from apps.integrations.tiktok import TikTokError
from apps.ledger import services as ledger
from apps.receiving import services as receiving
from apps.withdrawals import services as withdrawal_services
from apps.withdrawals.models import WithdrawalRequest

from .serializers import (
    AutofillDatasetSerializer,
    ConsentSerializer,
    CreatorProfileSerializer,
    DeviceSerializer,
    PhoneVerifySerializer,
    RefreshSerializer,
    SignalSerializer,
    TikTokExchangeSerializer,
    WithdrawalSerializer,
    WithdrawalTimelineSerializer,
)
from .tokens import issue_session, rotate_refresh_token


def client_ip(request) -> str | None:
    """عنوان العميل خلف وسيط عكسي."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def error(message: str, code: str = "domain_error", http_status=status.HTTP_400_BAD_REQUEST):
    """صيغة خطأ موحّدة يفهمها التطبيق."""
    return Response({"error": {"code": code, "message": message}}, status=http_status)


class TikTokExchangeView(APIView):
    """POST /api/v1/auth/tiktok/exchange — ضغطة «ابدأ بحساب TikTok»."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = TikTokExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            creator, account, created = integration_services.link_tiktok_account(
                data["code"],
                ip=client_ip(request),
                redirect_uri=data.get("redirect_uri", ""),
                code_verifier=data.get("code_verifier", ""),
            )
        except TikTokError as exc:
            return error(str(exc), code="tiktok_error")

        if creator.status == CreatorStatus.SUSPENDED:
            return error("الحساب موقوف", code="suspended", http_status=status.HTTP_403_FORBIDDEN)

        device_id = data.get("device_id", "")
        body = {
            "creator": {
                "id": str(creator.id),
                "display_name": creator.display_name,
                "avatar_url": account.avatar_url,
                "follower_count": account.follower_count,
            },
            "is_new": created,
            "phone_verified": creator.phone_verified_at is not None,
        }

        if creator.phone_verified_at is not None and device_id:
            device = CreatorDevice.objects.filter(
                creator=creator, device_id=device_id, is_active=True
            ).first()
            if device is not None:
                body["session"] = issue_session(creator, device)
                return Response(body, status=status.HTTP_200_OK)

        # قبل توثيق الهاتف يُمنح رمز تمهيدي قصير لا يفتح إلا مسار التحقق
        preauth, _ = tokens.issue(str(creator.id), tokens.TYPE_PREAUTH, device_id=device_id)
        body["preauth_token"] = preauth
        body["expires_in"] = settings.PREAUTH_TOKEN_MINUTES * 60
        return Response(body, status=status.HTTP_200_OK)


class PhoneVerifyView(APIView):
    """POST /api/v1/auth/phone/verify — بلا code يُرسل الرمز، ومعه يُتحقق منه."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        raw = request.headers.get("Authorization", "")
        if not raw.lower().startswith("bearer "):
            return error(
                "رمز تمهيدي مطلوب",
                code="preauth_required",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            payload = tokens.verify(raw.split()[1], tokens.TYPE_PREAUTH)
        except tokens.InvalidToken as exc:
            return error(str(exc), code="invalid_token", http_status=status.HTTP_401_UNAUTHORIZED)

        from apps.creators.models import Creator

        creator = Creator.objects.filter(pk=payload.subject).first()
        if creator is None:
            return error(
                "المبدع غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND
            )

        serializer = PhoneVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        code = data.get("code", "")

        try:
            if not code:
                creator_services.start_phone_verification(creator, data["phone"])
                return Response(
                    {"otp_sent": True, "expires_in": settings.OTP_TTL_MINUTES * 60},
                    status=status.HTTP_200_OK,
                )
            creator_services.confirm_phone_verification(creator, data["phone"], code)
        except DomainError as exc:
            return error(str(exc), code="phone_verification_failed")

        device_id = data.get("device_id") or payload.device_id
        device = None
        if device_id:
            device = creator_services.register_device(creator, device_id=device_id)

        return Response(
            {"phone_verified": True, "session": issue_session(creator, device)},
            status=status.HTTP_200_OK,
        )


class RefreshView(APIView):
    """POST /api/v1/auth/refresh — تجديد رمز الوصول برمز مربوط بالجهاز."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = rotate_refresh_token(serializer.validated_data["refresh"])
        except DomainError as exc:
            return error(str(exc), code="invalid_refresh", http_status=status.HTTP_401_UNAUTHORIZED)
        return Response({"session": session}, status=status.HTTP_200_OK)


class CreatorMeView(APIView):
    """GET /api/v1/creators/me — الملف والحالة والرصيد وآخر الطلبات."""

    permission_classes = [IsCreator]

    def get(self, request):
        creator = request.user.creator
        account = creator.platform_accounts.first()
        assignment = receiving.active_assignment(creator)
        recent = WithdrawalRequest.objects.filter(creator=creator).order_by("-initiated_at")[:5]

        payload = {
            "id": creator.id,
            "display_name": creator.display_name,
            "phone": creator.phone,
            "phone_verified": creator.phone_verified_at is not None,
            "status": creator.status,
            "preferred_language": creator.preferred_language,
            "setup_completed": bool(assignment and assignment.autofilled_at),
            "balance_egp": ledger.creator_balance(creator.id),
            "tiktok": (
                {
                    "display_name": account.display_name,
                    "avatar_url": account.avatar_url,
                    "follower_count": account.follower_count,
                }
                if account
                else None
            ),
            "recent_withdrawals": recent,
        }
        return Response(CreatorProfileSerializer(payload).data)


class ConsentView(APIView):
    """POST /api/v1/creators/me/consent — تسجيل الموافقة على الشروط."""

    permission_classes = [IsCreator]

    def post(self, request):
        serializer = ConsentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        consent = creator_services.record_consent(
            request.user.creator,
            terms_version=data["terms_version"],
            content_hash=data["content_hash"],
            ip=client_ip(request),
            device_fingerprint=data.get("device_fingerprint", ""),
            language=data.get("language", "ar"),
        )
        return Response(
            {"recorded": True, "accepted_at": consent.accepted_at}, status=status.HTTP_201_CREATED
        )


class DeviceView(APIView):
    """POST /api/v1/creators/me/devices — تسجيل الجهاز وسلامته ورمز إشعاراته."""

    permission_classes = [IsCreator]

    def post(self, request):
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            device = creator_services.register_device(
                request.user.creator,
                device_id=data["device_id"],
                integrity_token=data.get("integrity_token", ""),
                fcm_token=data.get("fcm_token", ""),
                model=data.get("model", ""),
                os_version=data.get("os_version", ""),
                app_version=data.get("app_version", ""),
                permissions=data.get("permissions") or {},
            )
        except DomainError as exc:
            return error(str(exc))
        return Response(
            {
                "device_id": device.device_id,
                "integrity_verdict": device.integrity_verdict,
                "trusted": device.is_trusted,
            },
            status=status.HTTP_201_CREATED,
        )


class AutofillDatasetView(APIView):
    """GET /api/v1/setup/autofill-dataset — بيانات حساب الاستلام المخصَّص."""

    permission_classes = [IsVerifiedCreator]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "setup"

    def get(self, request):
        try:
            assignment = receiving.assign_receiving_account(request.user.creator)
        except DomainError as exc:
            return error(
                str(exc),
                code="no_capacity",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        account = assignment.receiving_account
        payload = {
            "account_type": account.type,
            "identifier": account.identifier,
            "beneficiary_name": account.beneficiary_name or account.owner.full_name,
            "bank_name": account.bank_name,
        }
        return Response(AutofillDatasetSerializer(payload).data)


class SetupCompleteView(APIView):
    """POST /api/v1/setup/complete — إعلان أن التعبئة تمت داخل TikTok."""

    permission_classes = [IsVerifiedCreator]

    def post(self, request):
        creator = request.user.creator
        assignment = receiving.active_assignment(creator)
        if assignment is None:
            return error("لا يوجد حساب استلام مخصَّص بعد", code="no_assignment")

        receiving.mark_autofilled(assignment)
        if creator.status == CreatorStatus.NEW:
            creator.status = CreatorStatus.SETUP_COMPLETED
            creator.save(update_fields=["status", "updated_at"])

        return Response(
            {"setup_completed": True, "at": assignment.autofilled_at}, status=status.HTTP_200_OK
        )


class WithdrawalListCreateView(APIView):
    """POST /api/v1/withdrawals — ضغطة «سحب». GET — آخر الطلبات."""

    permission_classes = [IsVerifiedCreator]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "withdrawal"

    def get(self, request):
        requests_qs = WithdrawalRequest.objects.filter(creator=request.user.creator).order_by(
            "-initiated_at"
        )[:20]
        return Response(WithdrawalSerializer(requests_qs, many=True).data)

    def post(self, request):
        try:
            withdrawal = withdrawal_services.create_withdrawal(
                request.user.creator, request.user.device
            )
        except DomainError as exc:
            return error(str(exc), code="withdrawal_rejected")

        return Response(
            {
                "withdrawal": WithdrawalSerializer(withdrawal).data,
                # التطبيق يفتح TikTok بنفسه؛ الخادم لا ينفّذ شيئًا داخل TikTok
                "next_step": "open_tiktok_balance",
            },
            status=status.HTTP_201_CREATED,
        )


class WithdrawalDetailView(APIView):
    """GET /api/v1/withdrawals/{code} — حالة الطلب وخطه الزمني."""

    permission_classes = [IsVerifiedCreator]

    def get(self, request, code: str):
        withdrawal = WithdrawalRequest.objects.filter(
            creator=request.user.creator, code=code
        ).first()
        if withdrawal is None:
            return error("الطلب غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)
        return Response(WithdrawalTimelineSerializer(withdrawal).data)


class WithdrawalSignalView(APIView):
    """POST /api/v1/withdrawals/signals — إشارة من إشعارات TikTok على الجهاز."""

    permission_classes = [IsVerifiedCreator]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signal"

    def post(self, request):
        serializer = SignalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        package = data.get("package_name", "")
        # إشعار من حزمة غير حزم TikTok لا يُصدَّق مهما ادّعى
        sig_ok = bool(data.get("package_sig_ok")) and (
            not package or package in settings.TIKTOK_PACKAGE_NAMES
        )

        signal = withdrawal_services.ingest_signal(
            request.user.creator,
            source=data["source"],
            kind=data["kind"],
            payload=data.get("payload") or {},
            code=data.get("code", ""),
            amount=data.get("amount"),
            currency=data.get("currency", ""),
            txn_id=data.get("txn_id", ""),
            occurred_at=data.get("occurred_at"),
            package_sig_ok=sig_ok,
        )

        withdrawal = signal.request
        if withdrawal is not None:
            withdrawal.refresh_from_db()
        return Response(
            {
                "accepted": signal.is_trustworthy and withdrawal is not None,
                "withdrawal": WithdrawalSerializer(withdrawal).data if withdrawal else None,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class HealthView(APIView):
    """فحص حياة الواجهة."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "time": timezone.now()})
