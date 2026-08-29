"""سجل التدقيق — إلحاق فقط، يحفظ من فعل ماذا ومتى وبأي قيمة قبل وبعد."""
from django.db import models

from apps.common.enums import ActorType
from apps.common.errors import AppendOnlyViolation
from apps.common.models import TimestampedModel


class AuditLog(TimestampedModel):
    """كل تغيير ذي أثر مالي أو أمني يُكتب هنا ولا يُمحى."""

    actor_type = models.CharField(max_length=20, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    actor_label = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=80, db_index=True)
    entity = models.CharField(max_length=60, db_index=True)
    entity_id = models.UUIDField(null=True, blank=True, db_index=True)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        indexes = [models.Index(fields=["entity", "entity_id", "created_at"])]

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise AppendOnlyViolation("لا يجوز تعديل سجل التدقيق")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation("لا يجوز حذف سجل التدقيق")
