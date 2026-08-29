"""سجل التدقيق إلحاق فقط."""
import pytest
from django.db import ProgrammingError, transaction

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.common.errors import AppendOnlyViolation

pytestmark = pytest.mark.django_db


def test_record_writes_entry(creator):
    audit.record(action="test.action", entity="creator", entity_id=creator.id, after={"x": 1})
    assert AuditLog.objects.filter(action="test.action").count() == 1


def test_database_rejects_update_and_delete(creator):
    audit.record(action="test.action", entity="creator", entity_id=creator.id)
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            AuditLog.objects.all().update(action="tampered")
    with pytest.raises(ProgrammingError):
        with transaction.atomic():
            AuditLog.objects.all().delete()


def test_model_guard_blocks_delete(creator):
    log = audit.record(action="test.action", entity="creator", entity_id=creator.id)
    with pytest.raises(AppendOnlyViolation):
        log.delete()
