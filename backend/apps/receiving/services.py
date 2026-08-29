"""تخصيص حسابات الاستلام المصرية للمبدعين.

التخصيص من الخادم وحده. المبدع لا يرى الحساب ولا يختاره ولا يكتبه.
"""
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.audit import services as audit
from apps.common.enums import ActorType
from apps.common.errors import DomainError

from .models import (
    CreatorReceivingAssignment,
    OwnerStatus,
    ReceivingAccount,
    ReceivingAccountStatus,
)


class NoCapacityAvailable(DomainError):
    """لا يوجد حساب استلام شاغر — حالة تشغيلية تستدعي تدخل الإدارة."""


def active_assignment(creator) -> CreatorReceivingAssignment | None:
    """التخصيص الفعّال للمبدع إن وُجد."""
    return (
        CreatorReceivingAssignment.objects.select_related(
            "receiving_account", "receiving_account__owner"
        )
        .filter(creator=creator, active=True)
        .first()
    )


def _pick_account() -> ReceivingAccount:
    """اختيار أقل الحسابات تحميلًا ضمن سعته — توزيع عادل لا عشوائي."""
    candidates = (
        ReceivingAccount.objects.filter(
            status=ReceivingAccountStatus.ACTIVE, owner__status=OwnerStatus.ACTIVE
        )
        .annotate(assigned_count=Count("assignments", filter=Q(assignments__active=True)))
        .filter(assigned_count__lt=F("max_creators"))
        .order_by("assigned_count", "created_at")
    )
    account = candidates.first()
    if account is None:
        raise NoCapacityAvailable("لا يوجد حساب استلام متاح؛ يلزم إضافة حساب جديد")
    return account


@transaction.atomic
def assign_receiving_account(creator) -> CreatorReceivingAssignment:
    """إرجاع التخصيص الفعّال أو إنشاء واحد جديد."""
    existing = active_assignment(creator)
    if existing is not None:
        return existing

    account = _pick_account()
    assignment = CreatorReceivingAssignment.objects.create(
        creator=creator, receiving_account=account, assigned_at=timezone.now()
    )
    audit.record(
        action="receiving.assigned",
        entity="creator_receiving_assignment",
        entity_id=assignment.id,
        actor_type=ActorType.SYSTEM,
        after={"creator_id": str(creator.id), "receiving_account_id": str(account.id)},
    )
    return assignment


def mark_autofilled(assignment: CreatorReceivingAssignment) -> CreatorReceivingAssignment:
    """تسجيل أن بيانات الحساب عُبّئت داخل TikTok."""
    if assignment.autofilled_at is None:
        assignment.autofilled_at = timezone.now()
        assignment.save(update_fields=["autofilled_at", "updated_at"])
        audit.record(
            action="receiving.autofilled",
            entity="creator_receiving_assignment",
            entity_id=assignment.id,
            actor_type=ActorType.CREATOR,
            actor_id=assignment.creator_id,
        )
    return assignment


def mark_confirmed(assignment: CreatorReceivingAssignment) -> CreatorReceivingAssignment:
    """تسجيل أن أول تحويل وصل فعلًا عبر هذا التخصيص."""
    if assignment.confirmed_at is None:
        assignment.confirmed_at = timezone.now()
        assignment.save(update_fields=["confirmed_at", "updated_at"])
    return assignment
