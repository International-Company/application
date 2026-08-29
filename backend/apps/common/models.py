"""النماذج الأساسية المشتركة بين كل الوحدات."""
import uuid

from django.db import models


class TimestampedModel(models.Model):
    """معرّف UUID وطوابع زمنية — أساس كل جداول المنصة."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
