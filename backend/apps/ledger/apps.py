from django.apps import AppConfig


class LedgerConfig(AppConfig):
    """الدفتر المحاسبي"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ledger"
