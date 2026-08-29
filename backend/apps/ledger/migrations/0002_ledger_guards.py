"""حراس قاعدة البيانات للدفتر: منع التعديل والحذف، وفرض توازن كل قيد.

قيد CHECK في Postgres يرى صفًا واحدًا فقط، لذلك يُنفَّذ فحص التوازن عبر
CONSTRAINT TRIGGER مؤجَّل يعمل عند إغلاق المعاملة، بعد إدراج كل أسطر القيد.
"""
from django.db import migrations

APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION ledger_entries_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger_entries هو سجل إلحاق فقط: لا تعديل ولا حذف';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_entries_no_update
    BEFORE UPDATE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_entries_append_only();

CREATE TRIGGER ledger_entries_no_delete
    BEFORE DELETE ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_entries_append_only();
"""

APPEND_ONLY_FN_REVERSE = """
DROP TRIGGER IF EXISTS ledger_entries_no_update ON ledger_entries;
DROP TRIGGER IF EXISTS ledger_entries_no_delete ON ledger_entries;
DROP FUNCTION IF EXISTS ledger_entries_append_only();
"""

BALANCE_FN = """
CREATE OR REPLACE FUNCTION ledger_txn_must_balance() RETURNS trigger AS $$
DECLARE
    total_debit numeric(18,4);
    total_credit numeric(18,4);
BEGIN
    SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
      INTO total_debit, total_credit
      FROM ledger_entries
     WHERE txn_id = NEW.txn_id AND currency = NEW.currency;

    IF total_debit <> total_credit THEN
        RAISE EXCEPTION 'قيد غير متوازن للمعاملة % بعملة %: مدين % مقابل دائن %',
            NEW.txn_id, NEW.currency, total_debit, total_credit;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER ledger_entries_balanced
    AFTER INSERT ON ledger_entries
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ledger_txn_must_balance();
"""

BALANCE_FN_REVERSE = """
DROP TRIGGER IF EXISTS ledger_entries_balanced ON ledger_entries;
DROP FUNCTION IF EXISTS ledger_txn_must_balance();
"""

CURRENCY_FN = """
CREATE OR REPLACE FUNCTION ledger_entry_currency_matches_account() RETURNS trigger AS $$
DECLARE
    account_currency varchar(3);
BEGIN
    SELECT currency INTO account_currency FROM ledger_accounts WHERE id = NEW.account_id;
    IF account_currency IS DISTINCT FROM NEW.currency THEN
        RAISE EXCEPTION 'عملة السطر % لا تطابق عملة الحساب %', NEW.currency, account_currency;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ledger_entries_currency_check
    BEFORE INSERT ON ledger_entries
    FOR EACH ROW EXECUTE FUNCTION ledger_entry_currency_matches_account();
"""

CURRENCY_FN_REVERSE = """
DROP TRIGGER IF EXISTS ledger_entries_currency_check ON ledger_entries;
DROP FUNCTION IF EXISTS ledger_entry_currency_matches_account();
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]

    operations = [
        migrations.RunSQL(APPEND_ONLY_FN, APPEND_ONLY_FN_REVERSE),
        migrations.RunSQL(BALANCE_FN, BALANCE_FN_REVERSE),
        migrations.RunSQL(CURRENCY_FN, CURRENCY_FN_REVERSE),
    ]
