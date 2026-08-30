"""مسارات لوحة الإدارة.

كل مسار هنا يرفض رموز المبدعين رفضًا قاطعًا عبر IsAdminSession، والأفعال
المالية محصورة بأدوار محددة.
"""
from decimal import Decimal

from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db.models import Count, Q, Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.common.enums import ActorType, Currency
from apps.common.errors import DomainError
from apps.common.permissions import IsAdminSession
from apps.creators.models import Creator
from apps.identity import services as identity
from apps.identity.models import AdminRole
from apps.ledger.models import LedgerAccountType, LedgerEntry
from apps.payouts.models import PayoutMethod
from apps.payouts.services import execute_payout
from apps.pricing import services as pricing
from apps.pricing.models import FeeSchedule, FxRate
from apps.receiving.models import AccountOwner, CreatorReceivingAssignment, ReceivingAccount
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalRequest, WithdrawalStatus

from .admin_serializers import (
    AccountOwnerSerializer,
    AdminCreatorSerializer,
    AdminLoginSerializer,
    AdminWithdrawalSerializer,
    AssignmentSerializer,
    FeeScheduleSerializer,
    FxRateSerializer,
    PayoutExecuteSerializer,
    ReceivingAccountSerializer,
    TotpConfirmSerializer,
    WithdrawalActionSerializer,
)
from .views import client_ip, error

# من يملك تحريك المال
FINANCE_ROLES = {AdminRole.SUPERADMIN, AdminRole.FINANCE}
WRITE_ROLES = {AdminRole.SUPERADMIN, AdminRole.FINANCE, AdminRole.SUPPORT}


def require_role(user, allowed: set[str]) -> bool:
    return user.role in allowed


def forbidden(message: str = "صلاحيتك لا تسمح بهذا الإجراء"):
    return error(message, code="forbidden", http_status=status.HTTP_403_FORBIDDEN)


def actor_of(request) -> sm.Actor:
    return sm.Actor(type=ActorType.ADMIN, id=request.user.id, label=request.user.email)


# --- المصادقة ---------------------------------------------------------------

class CsrfView(APIView):
    """GET /api/v1/admin/auth/csrf — يضع كعكة CSRF قبل أي طلب كتابة."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class AdminLoginView(APIView):
    """POST /api/v1/admin/auth/login — بريد وكلمة مرور ورمز ثنائي."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "admin_auth"

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            user = identity.login(
                email=data["email"],
                password=data["password"],
                totp_code=data.get("totp_code", ""),
                ip=client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except identity.TotpRequired:
            return Response(
                {"totp_required": True}, status=status.HTTP_401_UNAUTHORIZED
            )
        except DomainError as exc:
            return error(str(exc), code="login_failed", http_status=status.HTTP_401_UNAUTHORIZED)

        django_login(request, user)
        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "totp_enabled": user.totp_enabled,
            }
        )


class AdminLogoutView(APIView):
    """POST /api/v1/admin/auth/logout."""

    permission_classes = [IsAdminSession]

    def post(self, request):
        django_logout(request)
        return Response({"logged_out": True})


class AdminMeView(APIView):
    """GET /api/v1/admin/auth/me."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "totp_enabled": user.totp_enabled,
            }
        )


class TotpSetupView(APIView):
    """POST /api/v1/admin/auth/totp — بدء الإعداد، ثم تأكيده برمز."""

    permission_classes = [IsAdminSession]

    def post(self, request):
        code = request.data.get("code")
        try:
            if code:
                serializer = TotpConfirmSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                identity.confirm_totp_setup(request.user, serializer.validated_data["code"])
                return Response({"totp_enabled": True})
            return Response(identity.start_totp_setup(request.user))
        except DomainError as exc:
            return error(str(exc), code="totp_failed")


# --- حسابات الاستلام وأصحابها ----------------------------------------------

class AccountOwnerListCreateView(APIView):
    """GET/POST /api/v1/admin/account-owners."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        owners = AccountOwner.objects.all().order_by("full_name")
        return Response(AccountOwnerSerializer(owners, many=True).data)

    def post(self, request):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        serializer = AccountOwnerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = serializer.save()
        audit.record(
            action="admin.owner_created",
            entity="account_owner",
            entity_id=owner.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            after=serializer.data,
            ip=client_ip(request),
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ReceivingAccountListCreateView(APIView):
    """GET/POST /api/v1/admin/receiving-accounts."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        accounts = (
            ReceivingAccount.objects.select_related("owner")
            .annotate(active_count=Count("assignments", filter=Q(assignments__active=True)))
            .order_by("created_at")
        )
        status_filter = request.query_params.get("status")
        if status_filter:
            accounts = accounts.filter(status=status_filter)
        return Response(ReceivingAccountSerializer(accounts, many=True).data)

    def post(self, request):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        serializer = ReceivingAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        audit.record(
            action="admin.receiving_account_created",
            entity="receiving_account",
            entity_id=account.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            after={"identifier": account.identifier, "type": account.type},
            ip=client_ip(request),
        )
        return Response(
            ReceivingAccountSerializer(account).data, status=status.HTTP_201_CREATED
        )


class ReceivingAccountDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/admin/receiving-accounts/{id}."""

    permission_classes = [IsAdminSession]

    def _get(self, pk):
        return ReceivingAccount.objects.select_related("owner").filter(pk=pk).first()

    def get(self, request, pk):
        account = self._get(pk)
        if account is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)
        return Response(ReceivingAccountSerializer(account).data)

    def patch(self, request, pk):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        account = self._get(pk)
        if account is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)
        before = ReceivingAccountSerializer(account).data
        serializer = ReceivingAccountSerializer(account, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit.record(
            action="admin.receiving_account_updated",
            entity="receiving_account",
            entity_id=account.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            before=before,
            after=serializer.data,
            ip=client_ip(request),
        )
        return Response(serializer.data)

    def delete(self, request, pk):
        """لا يُحذف حساب استلام أبدًا — يُوقَف فقط، حفاظًا على تتبّع الأموال."""
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        account = self._get(pk)
        if account is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)
        account.status = "paused"
        account.save(update_fields=["status", "updated_at"])
        audit.record(
            action="admin.receiving_account_paused",
            entity="receiving_account",
            entity_id=account.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            ip=client_ip(request),
        )
        return Response(ReceivingAccountSerializer(account).data)


class ReceivingAccountAssignView(APIView):
    """POST /api/v1/admin/receiving-accounts/{id}/assign — تخصيص لمبدع."""

    permission_classes = [IsAdminSession]

    def post(self, request, pk):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        account = ReceivingAccount.objects.filter(pk=pk).first()
        if account is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)

        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        creator = Creator.objects.filter(pk=serializer.validated_data["creator_id"]).first()
        if creator is None:
            return error(
                "المبدع غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND
            )

        if not account.has_capacity:
            return error("الحساب بلغ سعته أو ليس نشطًا", code="no_capacity")

        existing = CreatorReceivingAssignment.objects.filter(creator=creator, active=True).first()
        if existing is not None:
            if existing.receiving_account_id == account.id:
                return Response({"assigned": True, "changed": False})
            existing.active = False
            existing.deactivated_at = timezone.now()
            existing.deactivation_reason = f"إعادة تخصيص بقرار {request.user.email}"
            existing.save()

        assignment = CreatorReceivingAssignment.objects.create(
            creator=creator, receiving_account=account, assigned_at=timezone.now()
        )
        audit.record(
            action="admin.assignment_created",
            entity="creator_receiving_assignment",
            entity_id=assignment.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            after={"creator_id": str(creator.id), "receiving_account_id": str(account.id)},
            ip=client_ip(request),
        )
        return Response({"assigned": True, "changed": True}, status=status.HTTP_201_CREATED)


# --- المبدعون ---------------------------------------------------------------

class AdminCreatorListView(APIView):
    """GET /api/v1/admin/creators."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        creators = Creator.objects.prefetch_related(
            "platform_accounts", "assignments__receiving_account"
        ).order_by("-created_at")
        search = request.query_params.get("q")
        if search:
            creators = creators.filter(
                Q(display_name__icontains=search) | Q(phone__icontains=search)
            )
        status_filter = request.query_params.get("status")
        if status_filter:
            creators = creators.filter(status=status_filter)
        return Response(AdminCreatorSerializer(creators[:200], many=True).data)


# --- الطلبات ----------------------------------------------------------------

class AdminWithdrawalListView(APIView):
    """GET /api/v1/admin/withdrawals — الجدول اللحظي مع فلاتره."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        requests_qs = (
            WithdrawalRequest.objects.select_related(
                "creator", "receiving_account", "receiving_account__owner"
            )
            .prefetch_related("signals")
            .order_by("-initiated_at")
        )

        statuses = request.query_params.getlist("status")
        if statuses:
            requests_qs = requests_qs.filter(status__in=statuses)
        account = request.query_params.get("receiving_account")
        if account:
            requests_qs = requests_qs.filter(receiving_account_id=account)
        date_from = request.query_params.get("from")
        if date_from:
            requests_qs = requests_qs.filter(initiated_at__date__gte=date_from)
        date_to = request.query_params.get("to")
        if date_to:
            requests_qs = requests_qs.filter(initiated_at__date__lte=date_to)
        if request.query_params.get("conflicts") == "1":
            # الحالات المتعارضة: لم يصل، أو مرفوض، أو مضت مهلته وهو مفتوح
            requests_qs = requests_qs.filter(
                status__in=[WithdrawalStatus.NOT_RECEIVED, WithdrawalStatus.TIKTOK_REJECTED]
            )

        counts = {
            row["status"]: row["n"]
            for row in WithdrawalRequest.objects.values("status").annotate(n=Count("id"))
        }
        return Response(
            {
                "results": AdminWithdrawalSerializer(requests_qs[:300], many=True).data,
                "counts": counts,
                "server_time": timezone.now(),
            }
        )


class AdminWithdrawalDetailView(APIView):
    """GET/PATCH /api/v1/admin/withdrawals/{code}."""

    permission_classes = [IsAdminSession]

    def _get(self, code):
        return (
            WithdrawalRequest.objects.select_related(
                "creator", "receiving_account", "receiving_account__owner"
            )
            .filter(code=code)
            .first()
        )

    def get(self, request, code):
        withdrawal = self._get(code)
        if withdrawal is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)
        return Response(AdminWithdrawalSerializer(withdrawal).data)

    def patch(self, request, code):
        withdrawal = self._get(code)
        if withdrawal is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)

        serializer = WithdrawalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        action = data["action"]

        finance_actions = ("mark_received", "approve")
        if action in finance_actions and not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        if action == "cancel" and not require_role(request.user, WRITE_ROLES):
            return forbidden()

        try:
            if action == "mark_received":
                amount = data.get("amount_egp")
                if amount is None:
                    return error("المبلغ الواصل بالجنيه مطلوب", code="amount_required")
                withdrawal.fee_egp = pricing.compute_fee(Decimal(amount))
                withdrawal._via_state_machine = True
                withdrawal.save(update_fields=["fee_egp", "updated_at"])
                withdrawal._via_state_machine = False
                withdrawal = sm.transition(
                    withdrawal,
                    WithdrawalStatus.RECEIVED_EG,
                    actor=actor_of(request),
                    amount_egp=Decimal(amount),
                    evidence={"source": "admin", "note": data.get("note", "")},
                )
            elif action == "approve":
                withdrawal = sm.transition(
                    withdrawal,
                    WithdrawalStatus.APPROVED,
                    actor=actor_of(request),
                    evidence={"note": data.get("note", "")},
                )
            else:
                withdrawal = sm.transition(
                    withdrawal,
                    WithdrawalStatus.CANCELLED,
                    actor=actor_of(request),
                    evidence={"reason": data.get("reason", "قرار إداري")},
                )
        except DomainError as exc:
            return error(str(exc), code="transition_rejected")

        return Response(AdminWithdrawalSerializer(withdrawal).data)


class AdminPayoutExecuteView(APIView):
    """POST /api/v1/admin/payouts/{code}/execute."""

    permission_classes = [IsAdminSession]

    def post(self, request, code):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        withdrawal = WithdrawalRequest.objects.filter(code=code).first()
        if withdrawal is None:
            return error("غير موجود", code="not_found", http_status=status.HTTP_404_NOT_FOUND)

        serializer = PayoutExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        method = PayoutMethod.objects.filter(pk=data["method_id"], enabled=True).first()
        if method is None:
            return error("وسيلة الدفع غير متاحة", code="method_unavailable")

        try:
            payout = execute_payout(
                withdrawal,
                method=method,
                reference=data["reference"],
                executed_by=request.user,
                destination=data.get("destination", ""),
            )
        except DomainError as exc:
            return error(str(exc), code="payout_rejected")

        withdrawal.refresh_from_db()
        return Response(
            {
                "payout": {
                    "reference": payout.reference,
                    "gross": str(payout.gross_amount),
                    "fee": str(payout.fee_amount),
                    "net": str(payout.net_amount),
                    "executed_at": payout.executed_at,
                },
                "withdrawal": AdminWithdrawalSerializer(withdrawal).data,
            },
            status=status.HTTP_201_CREATED,
        )


class AdminPayoutQueueView(APIView):
    """GET /api/v1/admin/payouts — قائمة المعتمدة بانتظار التنفيذ."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        pending = (
            WithdrawalRequest.objects.select_related("creator", "receiving_account")
            .filter(status=WithdrawalStatus.APPROVED)
            .order_by("approved_at")
        )
        methods = PayoutMethod.objects.filter(enabled=True).values("id", "name", "provider")
        return Response(
            {
                "results": AdminWithdrawalSerializer(pending, many=True).data,
                "methods": list(methods),
            }
        )


# --- التقارير ---------------------------------------------------------------

class AdminReportsView(APIView):
    """GET /api/v1/admin/reports — الدفتر والحركة والرسوم."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        by_type = (
            LedgerEntry.objects.values("account__type", "currency")
            .annotate(debit=Sum("debit"), credit=Sum("credit"))
            .order_by("account__type")
        )
        ledger_summary = [
            {
                "type": row["account__type"],
                "currency": row["currency"],
                "debit": str(row["debit"] or Decimal("0")),
                "credit": str(row["credit"] or Decimal("0")),
                "balance": str((row["debit"] or Decimal("0")) - (row["credit"] or Decimal("0"))),
            }
            for row in by_type
        ]

        fees = LedgerEntry.objects.filter(account__type=LedgerAccountType.FEES).aggregate(
            total=Sum("credit")
        )["total"] or Decimal("0")

        liabilities = LedgerEntry.objects.filter(
            account__type=LedgerAccountType.CREATOR_BALANCE
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        outstanding = (liabilities["c"] or Decimal("0")) - (liabilities["d"] or Decimal("0"))

        daily = (
            WithdrawalRequest.objects.filter(received_at__isnull=False)
            .values("received_at__date")
            .annotate(count=Count("id"), total_egp=Sum("amount_egp"))
            .order_by("-received_at__date")[:30]
        )

        unbalanced = [
            str(row["txn_id"])
            for row in LedgerEntry.objects.values("txn_id", "currency").annotate(
                d=Sum("debit"), c=Sum("credit")
            )
            if row["d"] != row["c"]
        ]

        return Response(
            {
                "ledger": ledger_summary,
                "fees_collected_egp": str(fees),
                "outstanding_creator_balances_egp": str(outstanding),
                "currency": Currency.EGP,
                "daily_arrivals": [
                    {
                        "date": row["received_at__date"],
                        "count": row["count"],
                        "total_egp": str(row["total_egp"] or Decimal("0")),
                    }
                    for row in daily
                ],
                "status_counts": {
                    row["status"]: row["n"]
                    for row in WithdrawalRequest.objects.values("status").annotate(n=Count("id"))
                },
                "unbalanced_transactions": unbalanced,
            }
        )


# --- الإعدادات: الرسوم وسعر الصرف -------------------------------------------

class FeeScheduleView(APIView):
    """GET/POST /api/v1/admin/fee-schedules."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        schedules = FeeSchedule.objects.all().order_by("-effective_from")
        return Response(
            {
                "results": FeeScheduleSerializer(schedules, many=True).data,
                "active": FeeScheduleSerializer(pricing.active_fee_schedule()).data
                if pricing.active_fee_schedule()
                else None,
            }
        )

    def post(self, request):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        serializer = FeeScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = serializer.save()
        # جدول واحد فعّال في كل لحظة: ما سبقه يُغلق بوقت سريان الجديد
        FeeSchedule.objects.filter(is_active=True, effective_to__isnull=True).exclude(
            pk=schedule.pk
        ).update(effective_to=schedule.effective_from, is_active=False)
        audit.record(
            action="admin.fee_schedule_created",
            entity="fee_schedule",
            entity_id=schedule.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            after=serializer.data,
            ip=client_ip(request),
        )
        return Response(FeeScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


class FxRateView(APIView):
    """GET/POST /api/v1/admin/fx-rates."""

    permission_classes = [IsAdminSession]

    def get(self, request):
        rates = FxRate.objects.all().order_by("-effective_at")[:100]
        latest = pricing.latest_fx_rate()
        return Response(
            {
                "results": FxRateSerializer(rates, many=True).data,
                "latest": FxRateSerializer(latest).data if latest else None,
            }
        )

    def post(self, request):
        if not require_role(request.user, FINANCE_ROLES):
            return forbidden()
        serializer = FxRateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rate = serializer.save()
        audit.record(
            action="admin.fx_rate_created",
            entity="fx_rate",
            entity_id=rate.id,
            actor_type=ActorType.ADMIN,
            actor_id=request.user.id,
            actor_label=request.user.email,
            after=serializer.data,
            ip=client_ip(request),
        )
        return Response(FxRateSerializer(rate).data, status=status.HTTP_201_CREATED)
