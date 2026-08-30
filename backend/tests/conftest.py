"""تجهيزات مشتركة للاختبارات."""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.creators.models import Creator
from apps.pricing.models import FeeSchedule, FxRate
from apps.receiving.models import (
    AccountOwner,
    CreatorReceivingAssignment,
    ReceivingAccount,
    ReceivingAccountType,
)
from apps.withdrawals.models import WithdrawalRequest


@pytest.fixture
def creator(db) -> Creator:
    return Creator.objects.create(
        phone="+201000000001", display_name="مبدع تجريبي", phone_verified_at=timezone.now()
    )


@pytest.fixture
def other_creator(db) -> Creator:
    return Creator.objects.create(phone="+201000000002", display_name="مبدع آخر")


@pytest.fixture
def owner(db) -> AccountOwner:
    return AccountOwner.objects.create(full_name="صاحب حساب", whatsapp_phone="+201111111111")


@pytest.fixture
def receiving_account(db, owner) -> ReceivingAccount:
    return ReceivingAccount.objects.create(
        owner=owner,
        type=ReceivingAccountType.IPA,
        identifier="creator1@instapay",
        display_label="حساب الاستلام ١",
        daily_limit_egp=Decimal("100000"),
        monthly_limit_egp=Decimal("1000000"),
        max_creators=2,
    )


@pytest.fixture
def assignment(db, creator, receiving_account) -> CreatorReceivingAssignment:
    return CreatorReceivingAssignment.objects.create(
        creator=creator, receiving_account=receiving_account, assigned_at=timezone.now()
    )


@pytest.fixture
def fx_rate(db) -> FxRate:
    return FxRate.objects.create(rate=Decimal("48.500000"), effective_at=timezone.now())


@pytest.fixture
def fee_schedule(db) -> FeeSchedule:
    return FeeSchedule.objects.create(
        name="الرسوم القياسية",
        percent=Decimal("5.0000"),
        fixed_amount=Decimal("0"),
        effective_from=timezone.now(),
    )


@pytest.fixture
def request_initiated(db, creator, receiving_account, assignment) -> WithdrawalRequest:
    return WithdrawalRequest.objects.create(
        creator=creator,
        receiving_account=receiving_account,
        amount_usd=Decimal("100.0000"),
        amount_egp=Decimal("4850.0000"),
        fx_rate=Decimal("48.500000"),
        fee_egp=Decimal("242.5000"),
        initiated_at=timezone.now(),
    )


@pytest.fixture
def admin_client(db):
    """عميل إدارة بدور مالية — لأفعال المطابقة والدفع."""
    from rest_framework.test import APIClient

    from apps.identity.models import AdminRole, AdminUser

    user = AdminUser.objects.create_user(
        "recon@example.com", "pass-1234-secret", role=AdminRole.FINANCE, is_staff=True
    )
    api = APIClient()
    api.force_authenticate(user=user)
    return api
