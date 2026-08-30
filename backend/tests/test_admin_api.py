"""لوحة الإدارة: الدخول، الصلاحيات، حسابات الاستلام، الطلبات، الدفع، التقارير."""
from decimal import Decimal

import pyotp
import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.models import AdminRole, AdminUser
from apps.ledger.models import LedgerEntry
from apps.payouts.models import PayoutMethod
from apps.receiving.models import CreatorReceivingAssignment, ReceivingAccount
from apps.withdrawals import state_machine as sm
from apps.withdrawals.models import WithdrawalStatus as S

pytestmark = pytest.mark.django_db

PASSWORD = "pass-1234-secret"


@pytest.fixture
def finance_user(db) -> AdminUser:
    return AdminUser.objects.create_user(
        "finance@example.com", PASSWORD, role=AdminRole.FINANCE, is_staff=True
    )


@pytest.fixture
def viewer_user(db) -> AdminUser:
    return AdminUser.objects.create_user(
        "viewer@example.com", PASSWORD, role=AdminRole.VIEWER, is_staff=True
    )


@pytest.fixture
def admin(finance_user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=finance_user)
    return api


@pytest.fixture
def viewer(viewer_user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=viewer_user)
    return api


@pytest.fixture
def payout_method(db) -> PayoutMethod:
    return PayoutMethod.objects.create(name="إنستاباي يدوي", provider="manual")


# --- الدخول والتحقق الثنائي -------------------------------------------------

def test_login_with_correct_credentials(finance_user):
    api = APIClient()
    response = api.post(
        reverse("api_v1:api_admin:login"),
        {"email": finance_user.email, "password": PASSWORD},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["role"] == AdminRole.FINANCE
    assert response.data["totp_enabled"] is False


def test_login_with_wrong_password_is_rejected(finance_user):
    api = APIClient()
    response = api.post(
        reverse("api_v1:api_admin:login"),
        {"email": finance_user.email, "password": "wrong"},
        format="json",
    )
    assert response.status_code == 401
    from apps.identity.models import AdminLoginAttempt

    assert AdminLoginAttempt.objects.filter(succeeded=False).count() == 1


def test_repeated_failures_are_locked_out(finance_user, settings):
    settings.ADMIN_LOGIN_MAX_FAILURES = 3
    api = APIClient()
    url = reverse("api_v1:api_admin:login")
    for _ in range(3):
        api.post(url, {"email": finance_user.email, "password": "wrong"}, format="json")
    # حتى بكلمة المرور الصحيحة، الحساب مقفل داخل النافذة
    response = api.post(
        url, {"email": finance_user.email, "password": PASSWORD}, format="json"
    )
    assert response.status_code == 401
    assert "المحاولات" in response.data["error"]["message"]


def test_totp_setup_then_login_requires_code(finance_user, admin):
    setup = admin.post(reverse("api_v1:api_admin:totp"), {}, format="json")
    assert setup.status_code == 200
    secret = setup.data["secret"]
    assert setup.data["otpauth_uri"].startswith("otpauth://totp/")

    confirm = admin.post(
        reverse("api_v1:api_admin:totp"), {"code": pyotp.TOTP(secret).now()}, format="json"
    )
    assert confirm.data["totp_enabled"] is True

    fresh = APIClient()
    url = reverse("api_v1:api_admin:login")
    without = fresh.post(url, {"email": finance_user.email, "password": PASSWORD}, format="json")
    assert without.status_code == 401
    assert without.data["totp_required"] is True

    with_code = fresh.post(
        url,
        {
            "email": finance_user.email,
            "password": PASSWORD,
            "totp_code": pyotp.TOTP(secret).now(),
        },
        format="json",
    )
    assert with_code.status_code == 200


def test_wrong_totp_code_is_rejected(finance_user, admin):
    secret = admin.post(reverse("api_v1:api_admin:totp"), {}, format="json").data["secret"]
    admin.post(reverse("api_v1:api_admin:totp"), {"code": pyotp.TOTP(secret).now()}, format="json")
    fresh = APIClient()
    response = fresh.post(
        reverse("api_v1:api_admin:login"),
        {"email": finance_user.email, "password": PASSWORD, "totp_code": "000000"},
        format="json",
    )
    assert response.status_code == 401


# --- فصل الصلاحيات ----------------------------------------------------------

def test_anonymous_cannot_reach_admin_routes():
    api = APIClient()
    assert api.get(reverse("api_v1:api_admin:withdrawals")).status_code in (401, 403)


def test_creator_token_is_rejected_on_admin_routes(creator):
    """رمز مبدع صالح تمامًا لا يفتح أي مسار إداري."""
    from apps.api.tokens import issue_session
    from apps.creators.services import register_device

    device = register_device(creator, device_id="d-admin", integrity_token="t")
    session = issue_session(creator, device)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
    for name in ("withdrawals", "accounts", "reports", "creators", "payouts"):
        assert api.get(reverse(f"api_v1:api_admin:{name}")).status_code == 403


def test_viewer_can_read_but_not_write(viewer, owner):
    assert viewer.get(reverse("api_v1:api_admin:accounts")).status_code == 200
    response = viewer.post(
        reverse("api_v1:api_admin:accounts"),
        {"owner": str(owner.id), "type": "ipa", "identifier": "x@instapay", "max_creators": 1},
        format="json",
    )
    assert response.status_code == 403


# --- حسابات الاستلام --------------------------------------------------------

def test_create_receiving_account_and_assign_it(admin, owner, creator):
    created = admin.post(
        reverse("api_v1:api_admin:accounts"),
        {
            "owner": str(owner.id),
            "type": "ipa",
            "identifier": "new@instapay",
            "display_label": "حساب جديد",
            "beneficiary_name": "المستفيد",
            "max_creators": 2,
        },
        format="json",
    )
    assert created.status_code == 201
    account_id = created.data["id"]

    assigned = admin.post(
        reverse("api_v1:api_admin:account-assign", args=[account_id]),
        {"creator_id": str(creator.id)},
        format="json",
    )
    assert assigned.status_code == 201
    assignment = CreatorReceivingAssignment.objects.get(creator=creator, active=True)
    assert str(assignment.receiving_account_id) == account_id


def test_reassignment_deactivates_the_previous_one(admin, owner, creator, receiving_account):
    admin.post(
        reverse("api_v1:api_admin:account-assign", args=[receiving_account.id]),
        {"creator_id": str(creator.id)},
        format="json",
    )
    second = ReceivingAccount.objects.create(
        owner=owner, type="ipa", identifier="second@instapay", max_creators=1
    )
    admin.post(
        reverse("api_v1:api_admin:account-assign", args=[second.id]),
        {"creator_id": str(creator.id)},
        format="json",
    )
    assert CreatorReceivingAssignment.objects.filter(creator=creator, active=True).count() == 1
    active = CreatorReceivingAssignment.objects.get(creator=creator, active=True)
    assert active.receiving_account_id == second.id


def test_full_account_rejects_assignment(admin, creator, other_creator, receiving_account):
    receiving_account.max_creators = 1
    receiving_account.save()
    url = reverse("api_v1:api_admin:account-assign", args=[receiving_account.id])
    assert admin.post(url, {"creator_id": str(creator.id)}, format="json").status_code == 201
    second = admin.post(url, {"creator_id": str(other_creator.id)}, format="json")
    assert second.status_code == 400
    assert second.data["error"]["code"] == "no_capacity"


def test_delete_pauses_instead_of_removing(admin, receiving_account):
    response = admin.delete(
        reverse("api_v1:api_admin:account", args=[receiving_account.id])
    )
    assert response.status_code == 200
    receiving_account.refresh_from_db()
    assert receiving_account.status == "paused"
    assert ReceivingAccount.objects.filter(pk=receiving_account.pk).exists()


# --- الطلبات ---------------------------------------------------------------

def test_withdrawal_list_shows_evidence_and_counts(admin, request_initiated):
    from apps.withdrawals.models import SignalKind, SignalSource, WithdrawalSignal

    WithdrawalSignal.objects.create(
        request=request_initiated,
        creator=request_initiated.creator,
        source=SignalSource.NOTIFICATION,
        kind=SignalKind.PROCESSING,
        package_sig_ok=True,
        dedupe_key="k1",
    )
    response = admin.get(reverse("api_v1:api_admin:withdrawals"))
    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["code"] == request_initiated.code
    assert row["creator_name"] == request_initiated.creator.display_name
    assert row["evidence"][0]["trusted"] is True
    assert response.data["counts"][S.INITIATED] == 1


def test_filter_by_status(admin, request_initiated):
    sm.transition(request_initiated, S.TIKTOK_PROCESSING)
    empty = admin.get(reverse("api_v1:api_admin:withdrawals"), {"status": S.INITIATED})
    assert empty.data["results"] == []
    found = admin.get(reverse("api_v1:api_admin:withdrawals"), {"status": S.TIKTOK_PROCESSING})
    assert len(found.data["results"]) == 1


def test_mark_received_credits_the_creator(admin, request_initiated, fee_schedule):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    response = admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received", "amount_egp": "4850.0000"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["status"] == S.RECEIVED_EG
    assert response.data["fee_egp"] == "242.5000"

    from apps.ledger import services as ledger

    assert ledger.creator_balance(request_initiated.creator_id) == Decimal("4850.0000")


def test_mark_received_without_amount_is_refused(admin, request_initiated):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    response = admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received"},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "amount_required"
    assert LedgerEntry.objects.count() == 0


def test_admin_cannot_approve_before_arrival(admin, request_initiated):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    response = admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "approve"},
        format="json",
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "transition_rejected"


def test_viewer_cannot_move_money(viewer, request_initiated):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    response = viewer.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received", "amount_egp": "100"},
        format="json",
    )
    assert response.status_code == 403
    assert LedgerEntry.objects.count() == 0


def test_conflicts_filter_lists_problem_requests(admin, request_initiated):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    sm.transition(request_initiated, S.NOT_RECEIVED)
    response = admin.get(reverse("api_v1:api_admin:withdrawals"), {"conflicts": "1"})
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["status"] == S.NOT_RECEIVED


# --- الدفع ------------------------------------------------------------------

def test_payout_queue_then_execute(admin, request_initiated, payout_method, fee_schedule):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received", "amount_egp": "4850.0000"},
        format="json",
    )
    admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "approve"},
        format="json",
    )

    queue = admin.get(reverse("api_v1:api_admin:payouts"))
    assert len(queue.data["results"]) == 1
    assert len(queue.data["methods"]) == 1

    executed = admin.post(
        reverse("api_v1:api_admin:payout-execute", args=[request_initiated.code]),
        {"method_id": str(payout_method.id), "reference": "IPN-1", "destination": "0100"},
        format="json",
    )
    assert executed.status_code == 201
    assert executed.data["payout"]["net"] == "4607.5000"
    assert executed.data["withdrawal"]["status"] == S.PAID


def test_payout_requires_reference(admin, request_initiated, payout_method):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    sm.transition(request_initiated, S.RECEIVED_EG, amount_egp=Decimal("1000"))
    sm.transition(request_initiated, S.APPROVED)
    response = admin.post(
        reverse("api_v1:api_admin:payout-execute", args=[request_initiated.code]),
        {"method_id": str(payout_method.id), "reference": ""},
        format="json",
    )
    assert response.status_code == 400


def test_viewer_cannot_execute_payout(viewer, request_initiated, payout_method):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    sm.transition(request_initiated, S.RECEIVED_EG, amount_egp=Decimal("1000"))
    sm.transition(request_initiated, S.APPROVED)
    response = viewer.post(
        reverse("api_v1:api_admin:payout-execute", args=[request_initiated.code]),
        {"method_id": str(payout_method.id), "reference": "IPN-X"},
        format="json",
    )
    assert response.status_code == 403


# --- المبدعون والتقارير -----------------------------------------------------

def test_creators_list_and_search(admin, creator, other_creator):
    response = admin.get(reverse("api_v1:api_admin:creators"))
    assert len(response.data) == 2
    filtered = admin.get(reverse("api_v1:api_admin:creators"), {"q": creator.phone})
    assert len(filtered.data) == 1
    assert filtered.data[0]["balance_egp"] == "0.0000"


def test_reports_summarise_the_ledger(admin, request_initiated, payout_method, fee_schedule):
    sm.transition(request_initiated, S.TIKTOK_SENT)
    admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received", "amount_egp": "4850.0000"},
        format="json",
    )
    admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "approve"},
        format="json",
    )
    admin.post(
        reverse("api_v1:api_admin:payout-execute", args=[request_initiated.code]),
        {"method_id": str(payout_method.id), "reference": "IPN-R"},
        format="json",
    )

    response = admin.get(reverse("api_v1:api_admin:reports"))
    assert response.status_code == 200
    assert response.data["fees_collected_egp"] == "242.5000"
    assert response.data["outstanding_creator_balances_egp"] == "0.0000"
    assert response.data["unbalanced_transactions"] == []
    assert response.data["status_counts"][S.PAID] == 1
    assert len(response.data["daily_arrivals"]) == 1


def test_admin_actions_are_written_to_the_audit_log(admin, request_initiated, fee_schedule):
    from apps.audit.models import AuditLog

    sm.transition(request_initiated, S.TIKTOK_SENT)
    admin.patch(
        reverse("api_v1:api_admin:withdrawal", args=[request_initiated.code]),
        {"action": "mark_received", "amount_egp": "4850.0000"},
        format="json",
    )
    entry = AuditLog.objects.filter(action="withdrawal.received_eg").first()
    assert entry is not None
    assert entry.actor_type == "admin"
    assert entry.actor_label == "finance@example.com"


def test_server_time_is_returned_for_polling(admin):
    response = admin.get(reverse("api_v1:api_admin:withdrawals"))
    assert "server_time" in response.data
    assert response.data["server_time"] <= timezone.now()


def test_withdrawal_not_found(admin):
    response = admin.get(reverse("api_v1:api_admin:withdrawal", args=["WD-00000"]))
    assert response.status_code == 404
