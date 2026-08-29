"""الدفتر: التوازن، الإلحاق فقط، صحة الأرصدة."""
import uuid
from decimal import Decimal

import pytest
from django.db import ProgrammingError, connection, transaction

from apps.common.enums import Currency
from apps.common.errors import AppendOnlyViolation, UnbalancedTransaction
from apps.ledger import services as ledger
from apps.ledger.models import LedgerAccountType, LedgerEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def accounts(db, creator, receiving_account):
    return (
        ledger.get_or_create_account(
            type=LedgerAccountType.RECEIVING, ref_id=receiving_account.id, currency=Currency.EGP
        ),
        ledger.get_or_create_account(
            type=LedgerAccountType.CREATOR_BALANCE, ref_id=creator.id, currency=Currency.EGP
        ),
    )


def test_balanced_transaction_is_posted(accounts, creator):
    src, dst = accounts
    txn = ledger.post_transaction(
        [
            ledger.Line(account=src, debit=Decimal("4850")),
            ledger.Line(account=dst, credit=Decimal("4850")),
        ]
    )
    assert LedgerEntry.objects.filter(txn_id=txn).count() == 2
    assert ledger.creator_balance(creator.id) == Decimal("4850.0000")
    assert ledger.account_balance(src) == Decimal("4850.0000")


def test_service_rejects_unbalanced_transaction(accounts):
    src, dst = accounts
    with pytest.raises(UnbalancedTransaction):
        ledger.post_transaction(
            [
                ledger.Line(account=src, debit=Decimal("100")),
                ledger.Line(account=dst, credit=Decimal("90")),
            ]
        )
    assert LedgerEntry.objects.count() == 0


def test_service_rejects_single_line(accounts):
    src, _ = accounts
    with pytest.raises(UnbalancedTransaction):
        ledger.post_transaction([ledger.Line(account=src, debit=Decimal("100"))])


def test_service_rejects_line_that_is_both_debit_and_credit(accounts):
    src, dst = accounts
    with pytest.raises(UnbalancedTransaction):
        ledger.post_transaction(
            [
                ledger.Line(account=src, debit=Decimal("100"), credit=Decimal("100")),
                ledger.Line(account=dst, credit=Decimal("100")),
            ]
        )


def test_database_rejects_unbalanced_transaction_even_if_service_bypassed(accounts):
    """الحارس الحقيقي في قاعدة البيانات: قيد مؤجَّل يُفحص عند إغلاق المعاملة."""
    src, _ = accounts
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                txn_id=uuid.uuid4(),
                account=src,
                debit=Decimal("100"),
                credit=Decimal("0"),
                currency=Currency.EGP,
            )
            with connection.cursor() as cur:
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_database_rejects_update_of_ledger_entry(accounts):
    src, dst = accounts
    ledger.post_transaction(
        [
            ledger.Line(account=src, debit=Decimal("10")),
            ledger.Line(account=dst, credit=Decimal("10")),
        ]
    )
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            LedgerEntry.objects.all().update(debit=Decimal("999"))


def test_database_rejects_delete_of_ledger_entry(accounts):
    src, dst = accounts
    ledger.post_transaction(
        [
            ledger.Line(account=src, debit=Decimal("10")),
            ledger.Line(account=dst, credit=Decimal("10")),
        ]
    )
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            LedgerEntry.objects.all().delete()


def test_model_guard_blocks_delete_and_update(accounts):
    src, dst = accounts
    ledger.post_transaction(
        [
            ledger.Line(account=src, debit=Decimal("10")),
            ledger.Line(account=dst, credit=Decimal("10")),
        ]
    )
    entry = LedgerEntry.objects.first()
    with pytest.raises(AppendOnlyViolation):
        entry.delete()
    entry.debit = Decimal("50")
    with pytest.raises(AppendOnlyViolation):
        entry.save()


def test_currency_must_match_account(accounts):
    """سطر بعملة غير عملة الحساب مرفوض في قاعدة البيانات."""
    src, _ = accounts
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                txn_id=uuid.uuid4(),
                account=src,
                debit=Decimal("10"),
                currency=Currency.USD,
            )
