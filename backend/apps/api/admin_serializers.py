"""مسلسِلات لوحة الإدارة."""
from rest_framework import serializers

from apps.creators.models import Creator
from apps.receiving.models import AccountOwner, ReceivingAccount
from apps.withdrawals.models import WithdrawalRequest


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    totp_code = serializers.CharField(max_length=10, required=False, allow_blank=True)


class TotpConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=10)


class AccountOwnerSerializer(serializers.ModelSerializer):
    accounts_count = serializers.IntegerField(source="accounts.count", read_only=True)

    class Meta:
        model = AccountOwner
        fields = [
            "id",
            "full_name",
            "whatsapp_phone",
            "whatsapp_verified_at",
            "preferred_language",
            "status",
            "notes",
            "accounts_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "accounts_count"]


class ReceivingAccountSerializer(serializers.ModelSerializer):
    """حساب استلام مع حالة سعته الحالية."""

    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    owner_whatsapp = serializers.CharField(source="owner.whatsapp_phone", read_only=True)
    assigned_count = serializers.IntegerField(source="active_assignments_count", read_only=True)
    has_capacity = serializers.BooleanField(read_only=True)

    class Meta:
        model = ReceivingAccount
        fields = [
            "id",
            "owner",
            "owner_name",
            "owner_whatsapp",
            "type",
            "identifier",
            "display_label",
            "bank_name",
            "beneficiary_name",
            "daily_limit_egp",
            "monthly_limit_egp",
            "max_creators",
            "status",
            "assigned_count",
            "has_capacity",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "assigned_count", "has_capacity"]


class AssignmentSerializer(serializers.Serializer):
    """تخصيص حساب استلام لمبدع بقرار إداري."""

    creator_id = serializers.UUIDField()


class AdminCreatorSerializer(serializers.ModelSerializer):
    """المبدع كما تراه الإدارة."""

    tiktok_name = serializers.SerializerMethodField()
    receiving_account = serializers.SerializerMethodField()
    setup_completed = serializers.SerializerMethodField()
    balance_egp = serializers.SerializerMethodField()
    withdrawals_count = serializers.IntegerField(source="withdrawals.count", read_only=True)

    class Meta:
        model = Creator
        fields = [
            "id",
            "display_name",
            "phone",
            "phone_verified_at",
            "status",
            "risk_score",
            "preferred_language",
            "tiktok_name",
            "receiving_account",
            "setup_completed",
            "balance_egp",
            "withdrawals_count",
            "created_at",
        ]

    def get_tiktok_name(self, obj) -> str:
        account = obj.platform_accounts.first()
        return account.display_name if account else ""

    def get_receiving_account(self, obj) -> str:
        assignment = obj.assignments.filter(active=True).first()
        return str(assignment.receiving_account) if assignment else ""

    def get_setup_completed(self, obj) -> bool:
        return obj.assignments.filter(active=True, autofilled_at__isnull=False).exists()

    def get_balance_egp(self, obj) -> str:
        from apps.ledger import services as ledger

        return str(ledger.creator_balance(obj.id))


class AdminWithdrawalSerializer(serializers.ModelSerializer):
    """طلب سحب في جدول الإدارة اللحظي."""

    creator_name = serializers.CharField(source="creator.display_name", read_only=True)
    creator_phone = serializers.CharField(source="creator.phone", read_only=True)
    receiving_label = serializers.SerializerMethodField()
    owner_whatsapp = serializers.SerializerMethodField()
    elapsed_seconds = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "code",
            "status",
            "creator",
            "creator_name",
            "creator_phone",
            "receiving_label",
            "owner_whatsapp",
            "amount_usd",
            "amount_egp",
            "fee_egp",
            "net_amount_egp",
            "fx_rate",
            "tiktok_txn_id",
            "initiated_at",
            "processing_at",
            "sent_at",
            "received_at",
            "approved_at",
            "paid_at",
            "cancel_reason",
            "elapsed_seconds",
            "evidence",
        ]

    def get_receiving_label(self, obj) -> str:
        return str(obj.receiving_account) if obj.receiving_account else ""

    def get_owner_whatsapp(self, obj) -> str:
        if obj.receiving_account is None:
            return ""
        return obj.receiving_account.owner.whatsapp_phone

    def get_elapsed_seconds(self, obj) -> int:
        from django.utils import timezone

        end = obj.closed_at or timezone.now()
        return int((end - obj.initiated_at).total_seconds())

    def get_evidence(self, obj) -> list[dict]:
        """مصدر كل تأكيد — تراه الإدارة لتحكم على موثوقية الطلب."""
        return [
            {
                "source": signal.source,
                "kind": signal.kind,
                "amount": str(signal.parsed_amount) if signal.parsed_amount else None,
                "trusted": signal.is_trustworthy,
                "at": signal.created_at,
            }
            for signal in obj.signals.order_by("created_at")
        ]


class WithdrawalActionSerializer(serializers.Serializer):
    """أفعال الإدارة على طلب. كلها تمر عبر آلة الحالات."""

    ACTIONS = ["mark_received", "approve", "cancel"]

    action = serializers.ChoiceField(choices=ACTIONS)
    amount_egp = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, allow_null=True
    )
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class PayoutExecuteSerializer(serializers.Serializer):
    """تنفيذ الدفع بتسجيل مرجع التحويل."""

    method_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=120)
    destination = serializers.CharField(max_length=150, required=False, allow_blank=True)
