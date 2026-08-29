"""حقل نصي مشفَّر — يشفَّر عند الحفظ ويُفك عند القراءة."""
from django.db import models

from . import crypto


class EncryptedTextField(models.TextField):
    """يخزّن القيمة مشفّرة في القاعدة ويعرضها نصًا في بايثون."""

    description = "نص مشفَّر بـ AES-256-GCM"

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        return crypto.encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        return crypto.decrypt(value)
