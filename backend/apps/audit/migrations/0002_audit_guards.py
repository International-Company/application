"""سجل التدقيق إلحاق فقط — يُفرض في قاعدة البيانات لا في الكود وحده."""
from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log هو سجل إلحاق فقط: لا تعديل ولا حذف';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

CREATE TRIGGER audit_log_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
"""

SQL_REVERSE = """
DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;
DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;
DROP FUNCTION IF EXISTS audit_log_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [migrations.RunSQL(SQL, SQL_REVERSE)]
