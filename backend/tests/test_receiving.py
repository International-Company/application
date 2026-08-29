"""حسابات الاستلام وتخصيصها."""
import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.receiving.models import CreatorReceivingAssignment

pytestmark = pytest.mark.django_db


def test_creator_has_single_active_assignment(creator, assignment, receiving_account):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CreatorReceivingAssignment.objects.create(
                creator=creator, receiving_account=receiving_account, assigned_at=timezone.now()
            )


def test_reassignment_allowed_after_deactivation(creator, assignment, receiving_account):
    assignment.active = False
    assignment.deactivated_at = timezone.now()
    assignment.save()
    new_assignment = CreatorReceivingAssignment.objects.create(
        creator=creator, receiving_account=receiving_account, assigned_at=timezone.now()
    )
    assert new_assignment.active


def test_capacity_is_respected(receiving_account, assignment, other_creator):
    assert receiving_account.active_assignments_count == 1
    assert receiving_account.has_capacity  # السعة 2
    CreatorReceivingAssignment.objects.create(
        creator=other_creator, receiving_account=receiving_account, assigned_at=timezone.now()
    )
    assert not receiving_account.has_capacity
