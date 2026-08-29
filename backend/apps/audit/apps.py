from django.apps import AppConfig


class AuditConfig(AppConfig):
    """سجل التدقيق"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
